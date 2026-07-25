"""
Unit tests for WhatsApp message graph handlers
    . Loads on_message_graph_handler with stubbed config, graph runner, maps, and thread handling
    . Covers service-hours guard helpers, closed/offline messages, graph invocation, reset/debug, and payment simulation
    . Uses fake WhatsApp/message objects and mocked HTTP clients to avoid network and WA sends
  Functions/Classes:
    . FakeWa
    . FakeMessage
    . FakeAsyncClientFactory
    . handler_module
    . test_message_time_and_service_hours_guard
    . test_closed_and_offline_messages
    . test_handle_wa_msg_in_graph_runs_graph_with_typing_and_user_name
    . test_reset_thread_and_debug_state
    . test_simulate_payment_complete_no_order_and_success
"""

from types import ModuleType, SimpleNamespace

import pytest

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeWa:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


class FakeMessage:
    def __init__(self, sender="447000000001", text="hello", timestamp=None):
        self.sender = sender
        self.text = text
        self.timestamp = timestamp
        self.from_user = SimpleNamespace(name="Bas", wa_id=sender)
        self.location = SimpleNamespace(latitude=51.1, longitude=-0.1)
        self.typed = False

    async def indicate_typing(self):
        self.typed = True


class FakeResponse:
    history = []
    url = "https://ordelo.test/payment-hooks/payment-complete/"

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


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
def handler_module(monkeypatch):
    config_stub = build_config_stub()

    async def get_pool():
        return object()

    config_stub.pg_settings.get_pool = get_pool
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={"food_order": [{"order_id": "ORD-1", "payment_status": "requires_payment"}]}
    )

    runner_module = ModuleType("sfcs_agent.rest_agent.agent_runner")
    runner_module.run_calls = []

    async def run_rest_graph_with_custom_msg(**kwargs):
        runner_module.run_calls.append(kwargs)

    async def debug_state(recipient):
        return {"recipient": recipient, "active_agent": "triage_agent"}

    runner_module.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg
    runner_module.debug_state = debug_state

    params_module = ModuleType("restaurant_agent_core.config.params")

    class FakeSchedule:
        def __init__(self, open_value=True):
            self.open_value = open_value

        def is_open(self, dt):
            return self.open_value

        def format_today(self, dt):
            return "We open today at 5 pm."

    params_module.schedule = FakeSchedule(True)
    params_module.get_restaurant_master_cached = lambda *args, **kwargs: SimpleNamespace(
        service_hours=params_module.schedule
    )
    params_module.get_restaurant_base_url_async = lambda rest_ref: _async_base_url()

    async def _async_base_url():
        return "https://ordelo.test"

    maps_module = ModuleType("restaurant_agent_core.services.maps_service")
    maps_module.address_resolver = SimpleNamespace(
        get_address_from_coordinates=lambda lat, lon: {"lat": lat, "lon": lon}
    )

    thread_module = ModuleType("restaurant_agent_core.services.thread_management")
    thread_module.inactive = []

    class FakeThreadHandler:
        def __init__(self, pool):
            self.pool = pool

        async def make_threads_inactive(self, recipient):
            thread_module.inactive.append(recipient)

    thread_module.ThreadHandler = FakeThreadHandler

    module = load_module(
        "test_on_message_graph_handler_module",
        "restaurant_agent_core.watomation/on_message_graph_handler.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_core.config.params": params_module,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
            "restaurant_agent_core.services.maps_service": maps_module,
            "restaurant_agent_core.services.thread_management": thread_module,
        },
    )
    module.FlowButton = lambda **kwargs: SimpleNamespace(**kwargs)
    module._runner_module = runner_module
    module._params_module = params_module
    module._thread_module = thread_module
    return module


def test_message_time_and_service_hours_guard(handler_module):
    msg = FakeMessage(timestamp=1_778_326_200_000)
    assert handler_module._message_time_uk(msg).tzinfo is not None
    assert handler_module._message_time_uk(FakeMessage(timestamp="bad")) is None
    assert handler_module._message_time_uk(FakeMessage(timestamp=None)) is None

    handler_module._params_module.schedule.open_value = True
    assert handler_module.is_outside_service_hours(None, msg) is False

    handler_module._params_module.schedule.open_value = False
    assert handler_module.is_outside_service_hours(None, msg) is True
    assert handler_module.is_outside_service_hours(None, FakeMessage(sender="447448440754", timestamp=msg.timestamp)) is False


def test_format_debug_state(handler_module):
    assert handler_module._format_debug_state({"a": 1, "b": "two"}) == "*Debug State*\na: 1\nb: two"


@pytest.mark.asyncio
async def test_closed_and_offline_messages(handler_module):
    wa = FakeWa()
    msg = FakeMessage()

    await handler_module.send_closed_message(wa, msg)
    await handler_module.send_redirect_to_offline_mode(wa, msg)

    assert wa.sent_messages[0] == {
        "to": "447000000001",
        "text": "Thank you for your message. We open today at 5 pm.",
    }
    assert "going live" in wa.sent_messages[1]["text"]


@pytest.mark.asyncio
async def test_handle_wa_msg_in_graph_runs_graph_with_typing_and_user_name(handler_module):
    msg = FakeMessage(text="hi")

    await handler_module.handle_wa_msg_in_graph(FakeWa(), msg)

    assert msg.typed is True
    assert handler_module._runner_module.run_calls == [
        {"human_msg": "hi", "recipient": "447000000001", "wa_name": "Bas"}
    ]


@pytest.mark.asyncio
async def test_reset_thread_and_debug_state(handler_module):
    wa = FakeWa()
    msg = FakeMessage(sender="447448440754")

    await handler_module.reset_thread(wa, msg)
    assert handler_module._thread_module.inactive == ["447448440754"]
    assert wa.sent_messages[-1] == {"to": "447448440754", "text": "Starting new conversation"}

    await handler_module.handle_debug_state(wa, msg)
    assert "*Debug State*" in wa.sent_messages[-1]["text"]

    non_allowed = FakeWa()
    await handler_module.handle_debug_state(non_allowed, FakeMessage(sender="447000000001"))
    assert non_allowed.sent_messages == []


@pytest.mark.asyncio
async def test_simulate_payment_complete_no_order_and_success(monkeypatch, handler_module):
    wa = FakeWa()
    msg = FakeMessage()

    handler_module.client_ordelo = FakeSupabaseClient(table_data={"food_order": []})
    await handler_module.simulate_payment_complete(wa, msg)
    assert wa.sent_messages == [
        {"to": "447000000001", "text": "No order requiring payment found."}
    ]

    factory = FakeAsyncClientFactory()
    monkeypatch.setattr(handler_module.httpx, "AsyncClient", factory)
    handler_module.client_ordelo = FakeSupabaseClient(
        table_data={"food_order": [{"order_id": "ORD-1", "payment_status": "requires_payment"}]}
    )
    await handler_module.simulate_payment_complete(wa, msg)
    assert factory.posts == [
        {
            "url": "https://ordelo.test/payment-hooks/payment-complete/",
            "json": {"data": {"object": {"metadata": {"orderID": "ORD-1"}}}},
        }
    ]
