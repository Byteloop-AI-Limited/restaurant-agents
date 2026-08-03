"""Tests for persisted Thread-backed LangGraph configuration."""

from types import SimpleNamespace

import pytest

from restaurant_agent_runtime.services.thread_management import graph_config


class FakeThreadHandler:
    instances = []

    def __init__(self, pool, agent):
        self.pool = pool
        self.agent = agent
        self.inactive_recipients = []
        self.instances.append(self)

    async def make_threads_inactive(self, recipient):
        self.inactive_recipients.append(recipient)

    async def get_or_create_thread(self, recipient):
        return "thread-1", recipient == "new-recipient"


@pytest.fixture(autouse=True)
def fake_thread_handler(monkeypatch):
    FakeThreadHandler.instances.clear()
    monkeypatch.setattr(graph_config, "ThreadHandler", FakeThreadHandler)


@pytest.mark.asyncio
async def test_get_config_uses_restaurant_scoped_database_handler():
    pool = SimpleNamespace()

    config, created = await graph_config.get_config_for_recipient(
        "new-recipient",
        pool,
        agent="SFCS",
    )

    handler = FakeThreadHandler.instances[-1]
    assert handler.pool is pool
    assert handler.agent == "SFCS"
    assert created is True
    assert config == {
        "configurable": {
            "thread_id": "thread-1",
            "recipient": "new-recipient",
        }
    }


@pytest.mark.asyncio
async def test_force_new_thread_deactivates_existing_thread():
    await graph_config.get_config_for_recipient(
        "447000000001",
        SimpleNamespace(),
        agent="BNAT",
        force_new_thread=True,
    )

    assert FakeThreadHandler.instances[-1].inactive_recipients == ["447000000001"]

