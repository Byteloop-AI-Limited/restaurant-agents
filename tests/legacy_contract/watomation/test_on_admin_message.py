"""
Unit tests for admin WhatsApp message handlers
    . Loads on_admin_message with stubbed config, admin graph runner, and thread handler
    . Covers text, order, referred-product, and reset branches without external services
    . Uses fake WhatsApp/message objects and fake thread management
  Functions/Classes:
    . FakeWa
    . FakeMessage
    . admin_module
    . test_handle_wa_msg_in_admin_graph_runs_admin_graph
    . test_handle_admin_order_builds_out_of_stock_message
    . test_handle_admin_referred_product_builds_in_stock_message
    . test_reset_thread_admin_deactivates_thread_and_sends_message
"""

from types import ModuleType, SimpleNamespace

import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeWa:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


class FakeMessage:
    def __init__(self):
        self.sender = "447000000001"
        self.text = "hello admin"
        self.from_user = SimpleNamespace(wa_id=self.sender)
        self.order = SimpleNamespace(
            products=[SimpleNamespace(sku="sku_1"), SimpleNamespace(sku="sku_2")]
        )
        self.reply_to_message = SimpleNamespace(
            referred_product=SimpleNamespace(catalog_id="catalog-1", sku="sku_3")
        )
        self.typed = False

    async def indicate_typing(self):
        self.typed = True


@pytest.fixture
def admin_module(monkeypatch):
    config_stub = build_config_stub()

    async def get_pool():
        return object()

    config_stub.pg_settings.get_pool = get_pool

    runner_module = ModuleType("sfcs_agent.rest_agent.agent_runner")
    runner_module.run_calls = []

    async def run_admin_graph_with_custom_msg(**kwargs):
        runner_module.run_calls.append(kwargs)

    runner_module.run_admin_graph_with_custom_msg = run_admin_graph_with_custom_msg

    thread_module = ModuleType("restaurant_agent_core.services.thread_management")
    thread_module.inactive = []

    class ThreadHandler:
        def __init__(self, pool):
            self.pool = pool

        async def make_threads_inactive(self, recipient):
            thread_module.inactive.append(recipient)

    thread_module.ThreadHandler = ThreadHandler

    module = load_module(
        "test_on_admin_message_module",
        "restaurant_agent_core.watomation/on_admin_message.py",
        monkeypatch,
        {
            "config": config_stub,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
            "restaurant_agent_core.services.thread_management": thread_module,
        },
    )
    module._runner_module = runner_module
    module._thread_module = thread_module
    return module


@pytest.mark.asyncio
async def test_handle_wa_msg_in_admin_graph_runs_admin_graph(admin_module):
    msg = FakeMessage()

    await admin_module.handle_wa_msg_in_admin_graph(FakeWa(), msg)

    assert msg.typed is True
    assert admin_module._runner_module.run_calls == [
        {"recipient": "447000000001", "human_msg": "hello admin"}
    ]


@pytest.mark.asyncio
async def test_handle_admin_order_builds_out_of_stock_message(admin_module):
    msg = FakeMessage()

    await admin_module.handle_admin_order(FakeWa(), msg)

    assert msg.typed is True
    assert admin_module._runner_module.run_calls[-1] == {
        "recipient": "447000000001",
        "human_msg": "Update availability to `out of stock` for skus: [sku_1, sku_2]",
    }


@pytest.mark.asyncio
async def test_handle_admin_referred_product_builds_in_stock_message(admin_module):
    msg = FakeMessage()

    await admin_module.handle_admin_referred_product(FakeWa(), msg)

    assert msg.typed is True
    assert admin_module._runner_module.run_calls[-1] == {
        "recipient": "447000000001",
        "human_msg": "Update availability to `in stock` for sku: sku_3",
    }


@pytest.mark.asyncio
async def test_reset_thread_admin_deactivates_thread_and_sends_message(admin_module):
    wa = FakeWa()
    msg = FakeMessage()

    await admin_module.reset_thread_admin(wa, msg)

    assert admin_module._thread_module.inactive == ["447000000001"]
    assert wa.sent_messages == [
        {"to": "447000000001", "text": "Starting new conversation for admin"}
    ]
