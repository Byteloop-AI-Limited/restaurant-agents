"""
Unit tests for WhatsApp callback handlers
    . Loads on_callback_handler with stubbed config, graph runner, sender, and Ordelo service dependencies
    . Covers delivery address confirmation, service/rest/something-else routing, consent, admin collection ready, and order confirmation branches
    . Uses fake callback objects and mocked HTTP clients to avoid network and WhatsApp side effects
  Functions/Classes:
    . FakeCallbackData
    . FakeCallback
    . FakeAsyncClientFactory
    . callback_module
    . test_delivery_address_confirmation_yes_and_no
    . test_select_service_handler_branches
    . test_select_something_else_and_rest_ref_handlers
    . test_select_consent_handler_updates_ordelo_and_graph
    . test_admin_collection_ready_posts_to_ordelo
    . test_restaurant_order_confirmation_handler_accept_decline
"""

import json
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeCallbackData(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str


class FakeCallback:
    def __init__(self, data, recipient="447000000001"):
        self.data = json.dumps(data)
        self.from_user = SimpleNamespace(wa_id=recipient)


class FakeResponse:
    pass


class FakeAsyncClientFactory:
    def __init__(self):
        self.posts = []

    def __call__(self, *args, **kwargs):
        factory = self

        class FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                factory.posts.append({"url": url, "json": json})
                return FakeResponse()

        return FakeAsyncClient()


@pytest.fixture
def callback_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.project_settings.rest_ref = "ELAS"
    config_stub.project_settings.get_ordelo_url = lambda client: "https://ordelo.test"

    runner_module = ModuleType("sfcs_agent.rest_agent.agent_runner")
    runner_module.run_calls = []

    async def run_rest_graph_with_custom_msg(**kwargs):
        runner_module.run_calls.append(kwargs)

    runner_module.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg

    senders_module = ModuleType("sfcs_agent.rest_agent.agent_wa_senders")
    senders_module.CallbackButtonData = FakeCallbackData
    senders_module.service_calls = []
    senders_module.something_else_calls = []

    async def select_service_wa_send(recipient, wa_client, rest_ref):
        senders_module.service_calls.append((recipient, rest_ref))

    async def send_something_else_options_wa(recipient, wa_client, rest_ref):
        senders_module.something_else_calls.append((recipient, rest_ref))

    senders_module.select_service_wa_send = select_service_wa_send
    senders_module.send_something_else_options_wa = send_something_else_options_wa

    datamodel_module = ModuleType("restaurant_agent_core.services.ordelo_service.datamodels.customer_master_pymodel")

    class UpdateCustRestMapRequest(BaseModel):
        cust_id: str
        rest_ref: str
        has_consent: bool
        consent_dtts: object | None = None

    datamodel_module.UpdateCustRestMapRequest = UpdateCustRestMapRequest

    service_module = ModuleType("restaurant_agent_core.services.ordelo_service.ordelo_service")
    service_module.update_calls = []

    class OrdeloService:
        def __init__(self, rest_ref):
            self.rest_ref = rest_ref

        async def update_cust_rest_map(self, request):
            service_module.update_calls.append((self.rest_ref, request))
            return {"ok": True}

    service_module.OrdeloService = OrdeloService

    module = load_module(
        "test_on_callback_handler_module",
        "restaurant_agent_core.watomation/on_callback_handler.py",
        monkeypatch,
        {
            "config": config_stub,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
            "sfcs_agent.rest_agent.agent_wa_senders": senders_module,
            "restaurant_agent_core.services.ordelo_service.datamodels.customer_master_pymodel": datamodel_module,
            "restaurant_agent_core.services.ordelo_service.ordelo_service": service_module,
        },
    )
    module._runner_module = runner_module
    module._senders_module = senders_module
    module._service_module = service_module
    return module


@pytest.mark.asyncio
async def test_delivery_address_confirmation_yes_and_no(callback_module):
    await callback_module.delivery_address_confirmation(
        None,
        FakeCallback(
            {
                "action": "/ConfirmDeliveryAddress",
                "recipient": "447",
                "response": "Yes",
                "human_msg": "Yes, this is my address",
            }
        ),
    )
    assert callback_module._runner_module.run_calls[-1]["recipient"] == "447"
    assert callback_module._runner_module.run_calls[-1]["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_delivery_address_confirmed": True,
    }
    yes_msgs = callback_module._runner_module.run_calls[-1]["msgs"]
    assert yes_msgs[0].content == "Yes, this is my address"
    # A SystemMessage is appended instructing the agent to call calculate_min_order_value.
    assert len(yes_msgs) == 2
    assert "calculate_min_order_value" in yes_msgs[1].content

    await callback_module.delivery_address_confirmation(
        None,
        FakeCallback(
            {
                "action": "/ConfirmDeliveryAddress",
                "recipient": "447",
                "response": "No",
                "human_msg": "No, update it",
            }
        ),
    )
    call = callback_module._runner_module.run_calls[-1]
    assert call["state_update_dict"] == {
        "active_agent": "delivery_agent",
        "is_delivery_address_confirmed": False,
    }
    assert len(call["msgs"]) == 2


@pytest.mark.skip(reason="SFCS single-restaurant: no 'Please select the restaurant' branch")
@pytest.mark.asyncio
async def test_select_service_handler_branches(callback_module):
    missing = await callback_module.select_service_handler(
        object(),
        FakeCallback({"action": "/SelectService", "human_msg": "Delivery"}),
    )
    assert "Please select the restaurant" in missing
    assert callback_module._runner_module.run_calls[-1]["state_update_dict"] == {
        "rest_ref": None,
        "active_agent": "triage_agent",
    }

    await callback_module.select_service_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectService",
                "rest_ref": "elas",
                "active_agent": "triage_agent",
                "human_msg": "Something Else",
            }
        ),
    )
    assert callback_module._senders_module.something_else_calls == [("447000000001", "elas")]

    await callback_module.select_service_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectService",
                "rest_ref": "elas",
                "active_agent": "delivery_agent",
                "human_msg": "Delivery",
            }
        ),
    )
    assert callback_module._runner_module.run_calls[-1]["state_update_dict"] == {
        "rest_ref": "elas",
        "active_agent": "delivery_agent",
    }

    await callback_module.select_service_handler(
        object(),
        FakeCallback({"action": "/SelectService", "rest_ref": "elas", "human_msg": "Elai"}),
    )
    assert callback_module._senders_module.service_calls == [("447000000001", "elas")]


@pytest.mark.asyncio
@pytest.mark.skip(reason="SFCS lacks select_something_else_handler/select_rest_ref_handler (multi-rest only)")
async def test_select_something_else_and_rest_ref_handlers(callback_module):
    await callback_module.select_something_else_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectSomethingElse",
                "rest_ref": "elas",
                "active_agent": "triage_agent",
                "human_msg": "Something Else",
                "something_else_route": "numbered_menu",
            }
        ),
    )
    call = callback_module._runner_module.run_calls[-1]
    assert call["state_update_dict"] == {"rest_ref": "elas", "active_agent": "triage_agent"}
    assert "numbered list" in call["msgs"][1].content

    await callback_module.select_something_else_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectSomethingElse",
                "rest_ref": "elas",
                "active_agent": "dinein_agent",
                "human_msg": "Book Table",
            }
        ),
    )
    assert callback_module._runner_module.run_calls[-1]["state_update_dict"] == {
        "rest_ref": "elas",
        "active_agent": "dinein_agent",
    }

    await callback_module.select_rest_ref_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectRestRef",
                "rest_ref": "chks",
                "human_msg": "Wings and Things",
            }
        ),
    )
    call = callback_module._runner_module.run_calls[-1]
    assert call["state_update_dict"] == {"rest_ref": "chks", "active_agent": "triage_agent"}
    assert "Wings and Things" in call["msgs"][1].content


@pytest.mark.asyncio
async def test_select_consent_handler_updates_ordelo_and_graph(callback_module):
    await callback_module.select_consent_handler(
        object(),
        FakeCallback(
            {
                "action": "/SelectConsent",
                "response": "yes",
                "human_msg": "Yes, send updates",
            }
        ),
    )

    [(rest_ref, request)] = callback_module._service_module.update_calls
    assert rest_ref == "ELAS"
    assert request.cust_id == "447000000001"
    assert request.rest_ref == "ELAS"
    assert request.has_consent is True
    assert callback_module._runner_module.run_calls[-1]["state_update_dict"] == {
        "ask_for_consent": False,
        "active_agent": "triage_agent",
        "rest_ref": "elas",
    }


@pytest.mark.asyncio
async def test_admin_collection_ready_posts_to_ordelo(monkeypatch, callback_module):
    factory = FakeAsyncClientFactory()
    monkeypatch.setattr(callback_module.httpx, "AsyncClient", factory)

    await callback_module.admin_collection_ready(
        None,
        FakeCallback(
            {
                "action": "/AdminCollectionReady",
                "rider_id": "rider-1",
                "order_id": "ELAS-1",
            }
        ),
    )

    assert factory.posts == [
        {
            "url": "https://ordelo.test/delivery-hooks/notify-food-ready-for-pickup/rider-1",
            "json": {"restaurant_name": "Southern Fried Chicken - Salisbury", "order_number": "ELAS-1"},
        }
    ]


@pytest.mark.asyncio
async def test_restaurant_order_confirmation_handler_accept_decline(callback_module):
    assert await callback_module.restaurant_order_confirmation_handler(
        None,
        FakeCallback({"action": "/accept", "response": "ELAS-1"}),
    ) is None
    assert await callback_module.restaurant_order_confirmation_handler(
        None,
        FakeCallback({"action": "/decline", "response": "ELAS-1"}),
    ) is None
