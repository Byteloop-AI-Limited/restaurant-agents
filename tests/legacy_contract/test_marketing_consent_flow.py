"""
Unit tests for marketing-consent triage and callback behavior
    . Loads triage and callback modules with stubs to avoid heavy config imports
    . Covers terminate-conversation consent deferral and close-message behavior
    . Covers restaurant selection, service transfer, and consent button dispatch
    . Covers consent callback persistence, graph resume, decline, and invalid payload handling
  Functions/Classes:
    . DummyLogger
    . CallbackButtonDataStub
    . UpdateCustRestMapRequestStub
    . _load_module
    . _load_terminate_conversation
    . test_terminate_conversation_defers_for_consent
    . test_terminate_conversation_sends_requested_close_message
    . _build_triage_stubs
    . test_capture_restaurant_selected_sends_service_buttons
    . test_capture_restaurant_selected_transfers_on_explicit_service
    . test_capture_marketing_consent_sends_buttons
    . _build_callback_stubs
    . test_select_consent_handler_persists_and_resumes_graph
    . test_select_consent_handler_decline_persists_false
    . test_select_consent_handler_ignores_invalid_payload
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]


class DummyLogger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message):
        self.errors.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append((message, args, kwargs))


class CallbackButtonDataStub(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str


class UpdateCustRestMapRequestStub(BaseModel):
    cust_id: str
    rest_ref: str
    has_consent: bool
    consent_dtts: object | None = None


def _build_dedup_stub() -> ModuleType:
    """Passthrough stub for watomation.dedup so SimpleNamespace fakes need no .id."""
    module = ModuleType("restaurant_agent_runtime.watomation.dedup")
    module.wa_dedup = lambda fn: fn
    module._check_and_record = lambda _id: False
    return module


def _load_module(
    module_name: str, file_path: Path, monkeypatch, stubs: dict[str, ModuleType]
):
    stubs = {"restaurant_agent_runtime.watomation.dedup": _build_dedup_stub(), **stubs}
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_terminate_conversation(monkeypatch):
    """Load terminate_conversation from triage.py using stubs to avoid heavy config imports."""
    send_spy = []
    triage_module = _load_module(
        "test_triage_module_terminate",
        REPO_ROOT / "sfcs_agent.rest_agent/agents/triage.py",
        monkeypatch,
        _build_triage_stubs(send_spy),
    )
    return triage_module.terminate_conversation


@pytest.mark.asyncio
async def test_terminate_conversation_defers_for_consent(monkeypatch):
    _terminate_conversation = _load_terminate_conversation(monkeypatch)

    sent_messages = []
    inactive_recipients = []
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            recipient="447000000001",
            wa_client=SimpleNamespace(
                send_message=lambda **kwargs: sent_messages.append(kwargs)
            ),
            thread_handler=SimpleNamespace(
                make_threads_inactive=lambda recipient: inactive_recipients.append(
                    recipient
                )
            ),
        ),
    )

    async def _send_message(**kwargs):
        sent_messages.append(kwargs)

    async def _make_inactive(recipient):
        inactive_recipients.append(recipient)

    runtime.context.wa_client.send_message = _send_message
    runtime.context.thread_handler.make_threads_inactive = _make_inactive

    result = await _terminate_conversation.coroutine(
        reason_for_terminating_conversation="pickup_ready",
        message_to_be_sent_to_user="Your order is ready.",
        state={"ask_for_consent": True},
        tool_call_id="tool-1",
        runtime=runtime,
    )

    assert isinstance(result, str)
    assert "capture_marketing_consent" in result
    assert sent_messages == []
    assert inactive_recipients == []


@pytest.mark.asyncio
async def test_terminate_conversation_sends_requested_close_message(monkeypatch):
    _terminate_conversation = _load_terminate_conversation(monkeypatch)

    sent_messages = []
    inactive_recipients = []
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            recipient="447000000002",
            wa_client=SimpleNamespace(),
            thread_handler=SimpleNamespace(),
        ),
    )

    async def _send_message(**kwargs):
        sent_messages.append(kwargs)

    async def _make_inactive(recipient):
        inactive_recipients.append(recipient)

    runtime.context.wa_client.send_message = _send_message
    runtime.context.thread_handler.make_threads_inactive = _make_inactive

    command = await _terminate_conversation.coroutine(
        reason_for_terminating_conversation="delivery_complete",
        message_to_be_sent_to_user="Delivered successfully.",
        state={"ask_for_consent": False},
        tool_call_id="tool-2",
        runtime=runtime,
    )

    assert command.goto == "__end__"
    assert sent_messages == [
        {
            "to": "447000000002",
            "text": "Delivered successfully.\n\nThank you and good bye! 👋",
        }
    ]
    assert inactive_recipients == ["447000000002"]
    assert command.update["ask_for_consent"] is False


def _build_triage_stubs(send_spy):
    config_module = ModuleType("config")
    config_module.project_settings = SimpleNamespace(project_root=str(REPO_ROOT))

    langchain_agents_module = ModuleType("langchain.agents")
    langchain_agents_module.create_agent = lambda **kwargs: kwargs

    langchain_agents_middleware = ModuleType("langchain.agents.middleware")

    class ModelRequest:
        def __init__(self, state=None):
            self.state = state or {}

    def dynamic_prompt(fn):
        return fn

    langchain_agents_middleware.ModelRequest = ModelRequest
    langchain_agents_middleware.dynamic_prompt = dynamic_prompt

    harness_module = ModuleType("sfcs_agent.rest_agent.agents.agent_harness")
    harness_module.AgentState = dict
    harness_module.ContextSchema = object
    harness_module.cleanup_before_model = object()
    harness_module.respond_on_wa = object()
    harness_module.transfer_to_delivery = object()
    harness_module.transfer_to_takeaway = object()
    harness_module.transfer_to_dinein = object()

    senders_module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")

    async def select_service_wa_send(recipient, wa_client, rest_ref):
        send_spy.append(("service", recipient, rest_ref))

    async def select_rest_ref_wa_send(recipient, wa_client):
        send_spy.append(("restaurant", recipient, None))

    async def send_welcome_msg_wa(recipient, user_name, wa_client):
        send_spy.append(("welcome", recipient, user_name))

    async def select_marketing_consent_wa_send(recipient, wa_client, rest_ref):
        send_spy.append(("consent", recipient, rest_ref))

    senders_module.select_service_wa_send = select_service_wa_send
    senders_module.select_rest_ref_wa_send = select_rest_ref_wa_send
    senders_module.send_welcome_msg_wa = send_welcome_msg_wa
    senders_module.select_marketing_consent_wa_send = select_marketing_consent_wa_send

    lg_utils_module = ModuleType("restaurant_agent_runtime.services.lg_utils")
    lg_utils_module.llm_settings = SimpleNamespace(llm_client_single_tool_turn=object())

    return {
        "config": config_module,
        "langchain.agents": langchain_agents_module,
        "langchain.agents.middleware": langchain_agents_middleware,
        "sfcs_agent.rest_agent.agents.agent_harness": harness_module,
        "sfcs_agent.rest_agent.agent_wa_senders": senders_module,
        "restaurant_agent_runtime.services.lg_utils": lg_utils_module,
    }


@pytest.mark.asyncio
@pytest.mark.skip(reason="SFCS is single-restaurant; capture_restaurant_selected does not exist")
async def test_capture_restaurant_selected_sends_service_buttons(monkeypatch):
    send_spy = []
    triage_module = _load_module(
        "test_triage_module_buttons",
        REPO_ROOT / "sfcs_agent.rest_agent/agents/triage.py",
        monkeypatch,
        _build_triage_stubs(send_spy),
    )

    command = await triage_module.capture_restaurant_selected.coroutine(
        rest_ref="elas",
        state={"messages": [HumanMessage("Elai")]},
        tool_call_id="tool-3",
        runtime=SimpleNamespace(
            context=SimpleNamespace(recipient="447000000003", wa_client=object())
        ),
    )

    assert send_spy == [("service", "447000000003", "elas")]
    assert command.goto == "__end__"
    assert command.update["rest_ref"] == "elas"
    assert command.update["active_agent"] == "triage_agent"
    assert isinstance(command.update["messages"][-1], AIMessage)


@pytest.mark.asyncio
@pytest.mark.skip(reason="SFCS is single-restaurant; capture_restaurant_selected does not exist")
async def test_capture_restaurant_selected_transfers_on_explicit_service(monkeypatch):
    send_spy = []
    triage_module = _load_module(
        "test_triage_module_transfer",
        REPO_ROOT / "sfcs_agent.rest_agent/agents/triage.py",
        monkeypatch,
        _build_triage_stubs(send_spy),
    )

    command = await triage_module.capture_restaurant_selected.coroutine(
        rest_ref="chks",
        state={"messages": [HumanMessage("Wings delivery please")]},
        tool_call_id="tool-4",
        runtime=SimpleNamespace(
            context=SimpleNamespace(recipient="447000000004", wa_client=object())
        ),
    )

    assert send_spy == []
    assert command.graph == Command.PARENT
    assert command.goto == "delivery_agent"
    assert command.update["rest_ref"] == "chks"
    assert command.update["active_agent"] == "delivery_agent"


@pytest.mark.asyncio
async def test_capture_marketing_consent_sends_buttons(monkeypatch):
    send_spy = []
    triage_module = _load_module(
        "test_triage_module_consent",
        REPO_ROOT / "sfcs_agent.rest_agent/agents/triage.py",
        monkeypatch,
        _build_triage_stubs(send_spy),
    )

    command = await triage_module.capture_marketing_consent.coroutine(
        state={"ask_for_consent": True, "rest_ref": "elas"},
        tool_call_id="tool-5",
        runtime=SimpleNamespace(
            context=SimpleNamespace(recipient="447000000005", wa_client=object())
        ),
    )

    assert send_spy == [("consent", "447000000005", "elas")]
    assert command.goto == "__end__"
    assert (
        "Waiting for marketing consent response"
        in command.update["messages"][-1].content
    )


def _build_callback_stubs(run_calls, update_calls, logger):
    config_module = ModuleType("config")
    config_module.client_ordelo = object()
    config_module.logger = logger
    config_module.project_settings = SimpleNamespace(rest_ref="ELAS")

    agent_wa_senders = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    agent_wa_senders.CallbackButtonData = CallbackButtonDataStub

    agent_runner = ModuleType("sfcs_agent.rest_agent.agent_runner")

    async def run_rest_graph_with_custom_msg(recipient, msgs, state_update_dict):
        run_calls.append(
            {
                "recipient": recipient,
                "msgs": msgs,
                "state_update_dict": state_update_dict,
            }
        )

    agent_runner.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg

    request_module = ModuleType(
        "restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel"
    )
    request_module.UpdateCustRestMapRequest = UpdateCustRestMapRequestStub

    service_module = ModuleType("restaurant_agent_runtime.services.ordelo_service.ordelo_service")

    class OrdeloService:
        def __init__(self, rest_ref):
            self.rest_ref = rest_ref

        async def update_cust_rest_map(self, request):
            update_calls.append({"rest_ref": self.rest_ref, "request": request})
            return {"ok": True}

    service_module.OrdeloService = OrdeloService

    return {
        "config": config_module,
        "sfcs_agent.rest_agent.agent_wa_senders": agent_wa_senders,
        "sfcs_agent.rest_agent.agent_runner": agent_runner,
        "restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel": request_module,
        "restaurant_agent_runtime.services.ordelo_service.ordelo_service": service_module,
    }


@pytest.mark.asyncio
async def test_select_consent_handler_persists_and_resumes_graph(monkeypatch):
    run_calls = []
    update_calls = []
    logger = DummyLogger()
    callback_module = _load_module(
        "test_on_callback_handler_yes",
        REPO_ROOT / "restaurant_agent_runtime.watomation/on_callback_handler.py",
        monkeypatch,
        _build_callback_stubs(
            run_calls,
            update_calls,
            logger,
        ),
    )

    callback = SimpleNamespace(
        from_user=SimpleNamespace(wa_id="447000000006"),
        data=json.dumps(
            {
                "action": "/SelectConsent",
                "rest_ref": "chks",
                "response": "yes",
                "human_msg": "Yes, send me marketing updates",
            }
        ),
    )

    await callback_module.select_consent_handler(SimpleNamespace(), callback)

    assert len(update_calls) == 1
    request = update_calls[0]["request"]
    assert request.cust_id == "447000000006"
    assert request.rest_ref == "ELAS"
    assert request.has_consent is True

    assert len(run_calls) == 1
    run_call = run_calls[0]
    assert run_call["recipient"] == "447000000006"
    assert run_call["state_update_dict"]["ask_for_consent"] is False
    assert run_call["state_update_dict"]["rest_ref"] == "elas"
    assert isinstance(run_call["msgs"][0], HumanMessage)
    assert isinstance(run_call["msgs"][1], SystemMessage)
    assert "terminate_conversation" in run_call["msgs"][1].content


@pytest.mark.asyncio
async def test_select_consent_handler_decline_persists_false(monkeypatch):
    run_calls = []
    update_calls = []
    logger = DummyLogger()
    callback_module = _load_module(
        "test_on_callback_handler_no",
        REPO_ROOT / "restaurant_agent_runtime.watomation/on_callback_handler.py",
        monkeypatch,
        _build_callback_stubs(
            run_calls,
            update_calls,
            logger,
        ),
    )

    callback = SimpleNamespace(
        from_user=SimpleNamespace(wa_id="447000000007"),
        data=json.dumps(
            {
                "action": "/SelectConsent",
                "rest_ref": "elas",
                "response": "no",
                "human_msg": "No, thanks",
            }
        ),
    )

    await callback_module.select_consent_handler(SimpleNamespace(), callback)

    assert len(update_calls) == 1
    request = update_calls[0]["request"]
    assert request.rest_ref == "ELAS"
    assert request.has_consent is False
    assert len(run_calls) == 1
    assert run_calls[0]["state_update_dict"]["ask_for_consent"] is False


@pytest.mark.asyncio
async def test_select_consent_handler_ignores_invalid_payload(monkeypatch):
    run_calls = []
    update_calls = []
    logger = DummyLogger()
    callback_module = _load_module(
        "test_on_callback_handler_invalid",
        REPO_ROOT / "restaurant_agent_runtime.watomation/on_callback_handler.py",
        monkeypatch,
        _build_callback_stubs(
            run_calls,
            update_calls,
            logger,
        ),
    )

    callback = SimpleNamespace(
        from_user=SimpleNamespace(wa_id="447000000008"),
        data=json.dumps({"rest_ref": "elas", "response": "yes"}),
    )

    await callback_module.select_consent_handler(SimpleNamespace(), callback)

    assert run_calls == []
    assert update_calls == []
    assert logger.errors
