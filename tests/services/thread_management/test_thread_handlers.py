"""
Unit tests for in-memory thread handlers in services.thread_handlers
    . Verifies thread creation, lookup, deactivation and get_or_create flow
    . Operates entirely on the in-memory thread_dict — no database needed
    . Resets thread_dict between tests so state does not leak
  Functions/Classes:
    . _reset_thread_dict
    . test_create_new_entry_adds_active_thread
    . test_add_new_thread_marks_existing_inactive
    . test_get_active_thread_returns_none_for_unknown_number
    . test_thread_handler_local_create_thread_returns_dict
    . test_thread_handler_local_make_threads_inactive_counts
    . test_thread_handler_local_get_or_create_creates_when_missing
    . test_thread_handler_local_get_or_create_reuses_active
"""

import pytest

from restaurant_agent_core.services import thread_handlers


@pytest.fixture(autouse=True)
def _reset_thread_dict():
    thread_handlers.thread_dict.clear()
    yield
    thread_handlers.thread_dict.clear()


def test_create_new_entry_adds_active_thread():
    thread = thread_handlers.create_new_entry("447000000001")

    assert thread["is_active"] is True
    assert "thread_id" in thread
    assert thread_handlers.thread_dict["447000000001"][-1]["is_active"] is True


def test_add_new_thread_marks_existing_inactive():
    first = thread_handlers.create_new_entry("447000000001")
    second = thread_handlers.add_new_thread("447000000001")

    assert second["thread_id"] != first["thread_id"]
    assert thread_handlers.thread_dict["447000000001"][0]["is_active"] is False
    assert thread_handlers.thread_dict["447000000001"][1]["is_active"] is True


def test_get_active_thread_returns_none_for_unknown_number():
    assert thread_handlers.get_active_thread("447000000099") is None


@pytest.mark.asyncio
async def test_thread_handler_local_create_thread_returns_dict():
    handler = thread_handlers.ThreadHandlerLocal()

    result = await handler.create_thread("447000000001")

    assert result["from_number"] == "447000000001"
    assert result["is_active"] is True
    assert isinstance(result["thread_id"], str)


@pytest.mark.asyncio
async def test_thread_handler_local_make_threads_inactive_counts():
    handler = thread_handlers.ThreadHandlerLocal()
    await handler.create_thread("447000000001")

    result = await handler.make_threads_inactive("447000000001")

    assert "1 thread" in result["message"]
    assert thread_handlers.thread_dict["447000000001"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_thread_handler_local_make_threads_inactive_unknown_number():
    handler = thread_handlers.ThreadHandlerLocal()

    result = await handler.make_threads_inactive("447099999999")

    assert "0 thread" in result["message"]


@pytest.mark.asyncio
async def test_thread_handler_local_get_or_create_creates_when_missing():
    handler = thread_handlers.ThreadHandlerLocal()

    thread_id, created = await handler.get_or_create_thread("447000000001")

    assert created is True
    assert thread_id


@pytest.mark.asyncio
async def test_thread_handler_local_get_or_create_reuses_active():
    handler = thread_handlers.ThreadHandlerLocal()
    first_id, _ = await handler.get_or_create_thread("447000000001")

    second_id, created = await handler.get_or_create_thread("447000000001")

    assert created is False
    assert first_id == second_id
