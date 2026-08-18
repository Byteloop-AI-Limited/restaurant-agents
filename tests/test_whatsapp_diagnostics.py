"""Tests for the bounded production WhatsApp diagnostic surface."""

from types import SimpleNamespace

import pytest

from restaurant_agent_runtime.watomation import on_message_graph_handler as handlers
from restaurant_agent_runtime.web.app_factory import (
    AgentBindings,
    _register_whatsapp_handlers,
)


class FakeThreadHandler:
    instances = []

    def __init__(self, pool, agent):
        self.pool = pool
        self.agent = agent
        self.inactive = []
        self.instances.append(self)

    async def make_threads_inactive(self, recipient):
        self.inactive.append(recipient)


class FakeDatabase:
    def __init__(self):
        self.pool = object()
        self.calls = 0

    async def get_pool(self):
        self.calls += 1
        return self.pool


class FakeWhatsApp:
    def __init__(self):
        self.sent = []
        self.handlers = []

    def add_handlers(self, *registered_handlers):
        self.handlers.extend(registered_handlers)

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


def test_adhoc_order_reset_commands_are_not_part_of_shared_handler_module():
    for name in (
        "WHEN_ADHOC_TEST",
        "WHEN_ADHOC_TEST_TAKEAWAY",
        "handle_adhoc_test",
        "handle_adhoc_test_takeaway",
    ):
        assert not hasattr(handlers, name)


def test_standard_message_registration_includes_only_payment_simulation():
    wa = FakeWhatsApp()
    runtime = SimpleNamespace(
        async_wa_client=wa,
        presentation=SimpleNamespace(restaurant_selection=None),
    )

    _register_whatsapp_handlers(
        runtime=runtime,
        graph_adapter=SimpleNamespace(),
        bindings=AgentBindings(
            callback_data_type=dict,
            select_service_sender=lambda **_: None,
        ),
    )

    assert [handler._callback.__name__ for handler in wa.handlers[:6]] == [
        "bound_reset",
        "bound_closed_message",
        "bound_location",
        "bound_payment_complete",
        "bound_debug",
        "bound_graph",
    ]


@pytest.mark.asyncio
async def test_payment_simulation_uses_exact_runtime_database_and_ordelo_hook(
    monkeypatch,
):
    class FakeQuery:
        def select(self, *columns):
            assert columns == ("order_id, payment_status",)
            return self

        def eq(self, column, value):
            assert (column, value) == ("recipient", "447000000002")
            return self

        def order(self, column, *, desc):
            assert (column, desc) == ("order_dtts", True)
            return self

        def limit(self, value):
            assert value == 1
            return self

        def execute(self):
            return SimpleNamespace(
                data=[{"order_id": "ORDER-1", "payment_status": "requires_payment"}]
            )

    class FakeDatabaseClient:
        def table(self, table_name):
            assert table_name == "food_order"
            return FakeQuery()

    class FakeResponse:
        is_redirect = False

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "success"}

    class FakeHttpClient:
        calls = []

        def __init__(self, *, follow_redirects):
            assert follow_redirects is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, json):
            self.calls.append((url, json))
            return FakeResponse()

    database_client = FakeDatabaseClient()

    class FakeOperationalLookups:
        def get_app_url(self, app_ref):
            assert app_ref == "ORDELO"
            return "https://ordelo.example.test"

    runtime = SimpleNamespace(
        settings=SimpleNamespace(database_client=database_client),
        operational_lookups=FakeOperationalLookups(),
    )
    monkeypatch.setattr(handlers.httpx, "AsyncClient", FakeHttpClient)

    await handlers.simulate_payment_complete(
        FakeWhatsApp(),
        SimpleNamespace(sender="447000000002"),
        runtime=runtime,
    )

    assert FakeHttpClient.calls == [
        (
            "https://ordelo.example.test/payment-hooks/payment-complete",
            {"data": {"object": {"metadata": {"orderID": "ORDER-1"}}}},
        )
    ]


@pytest.mark.asyncio
async def test_reset_uses_exact_runtime_database(monkeypatch):
    FakeThreadHandler.instances.clear()
    monkeypatch.setattr(handlers, "ThreadHandler", FakeThreadHandler)
    database = FakeDatabase()
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        settings=SimpleNamespace(database=database),
        operational_lookups=SimpleNamespace(
            is_overwatch_recipient=lambda recipient: recipient == "447000000001"
        ),
    )
    wa = FakeWhatsApp()
    msg = SimpleNamespace(
        id="message-1",
        from_user=SimpleNamespace(wa_id="447000000001"),
    )

    await handlers.reset_thread(wa, msg, runtime=runtime)

    thread_handler = FakeThreadHandler.instances[-1]
    assert database.calls == 1
    assert thread_handler.pool is database.pool
    assert thread_handler.agent == "BNAT"
    assert thread_handler.inactive == ["447000000001"]
    assert wa.sent == [
        {"to": "447000000001", "text": "Starting new conversation"}
    ]


@pytest.mark.asyncio
async def test_reset_is_blocked_for_non_overwatch_customer(monkeypatch):
    FakeThreadHandler.instances.clear()
    monkeypatch.setattr(handlers, "ThreadHandler", FakeThreadHandler)
    database = FakeDatabase()
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        settings=SimpleNamespace(database=database),
        operational_lookups=SimpleNamespace(is_overwatch_recipient=lambda _: False),
    )
    wa = FakeWhatsApp()
    msg = SimpleNamespace(
        id="message-reset-non-overwatch",
        from_user=SimpleNamespace(wa_id="447000000002"),
    )

    await handlers.reset_thread(wa, msg, runtime=runtime)

    assert database.calls == 0
    assert FakeThreadHandler.instances == []
    assert wa.sent == [
        {
            "to": "447000000002",
            "text": "Reset is not available. Please continue in this conversation.",
        }
    ]
