"""
Unit tests for the Postgres-backed ThreadHandler
    . Loads thread_handler.py with stubbed config to avoid live settings
    . Uses FakeAsyncPool to capture SQL parameters and return canned rows
    . Verifies each handler method invokes the expected Postgres function
  Functions/Classes:
    . _build_handler
    . test_create_thread_executes_sql
    . test_get_active_thread_returns_fetchone
    . test_make_threads_inactive_message_uses_affected_rows
    . test_get_stale_active_threads_returns_fetchall
    . test_get_or_create_thread_returns_tuple
    . test_retain_thread_executes_sql
"""

import pytest

from tests._stubs.loader import load_module
from tests._stubs.pool_stub import FakeAsyncPool


@pytest.fixture
def thread_handler_module(monkeypatch):
    return load_module(
        "test_thread_handler_module",
        "restaurant_agent_runtime.services/thread_management/thread_handler.py",
        monkeypatch,
    )


def _build_handler(module, fetchone=None, fetchall=None):
    pool = FakeAsyncPool(fetchone_result=fetchone, fetchall_result=fetchall or [])
    handler = module.ThreadHandler(pool=pool, agent="ELAS")
    return handler, pool


@pytest.mark.asyncio
async def test_create_thread_executes_sql(thread_handler_module):
    handler, pool = _build_handler(thread_handler_module, fetchone={"thread_id": "t-1"})

    result = await handler.create_thread("447000000001")

    assert result == {"thread_id": "t-1"}
    sql, params = pool.cursor_obj.executed[0]
    assert "create_thread" in sql
    assert params == ("ELAS", "447000000001")


@pytest.mark.asyncio
async def test_get_active_thread_returns_fetchone(thread_handler_module):
    handler, pool = _build_handler(thread_handler_module, fetchone={"thread_id": "t-2"})

    result = await handler.get_active_thread("447000000001")

    assert result == {"thread_id": "t-2"}
    assert "get_active_thread" in pool.cursor_obj.executed[0][0]


@pytest.mark.asyncio
async def test_make_threads_inactive_message_uses_affected_rows(thread_handler_module):
    handler, pool = _build_handler(thread_handler_module, fetchone=(3,))

    result = await handler.make_threads_inactive("447000000001")

    assert result == {"message": "3 thread(s) marked as inactive."}
    assert "make_threads_inactive" in pool.cursor_obj.executed[0][0]


@pytest.mark.asyncio
async def test_make_threads_inactive_handles_no_result(thread_handler_module):
    handler, _ = _build_handler(thread_handler_module, fetchone=None)

    result = await handler.make_threads_inactive("447000000001")

    assert result == {"message": "0 thread(s) marked as inactive."}


@pytest.mark.asyncio
async def test_get_stale_active_threads_returns_fetchall(thread_handler_module):
    rows = [{"thread_id": "t-1"}, {"thread_id": "t-2"}]
    handler, pool = _build_handler(thread_handler_module, fetchall=rows)

    result = await handler.get_stale_active_threads(stale_minutes=10)

    assert result == rows
    sql, params = pool.cursor_obj.executed[0]
    assert "get_stale_active_threads" in sql
    assert params == ("ELAS", 10)


@pytest.mark.asyncio
async def test_get_or_create_thread_returns_tuple(thread_handler_module):
    handler, _ = _build_handler(
        thread_handler_module,
        fetchone={"thread_id": "t-3", "was_created": True},
    )

    thread_id, created = await handler.get_or_create_thread("447000000001")

    assert thread_id == "t-3"
    assert created is True


@pytest.mark.asyncio
async def test_get_or_create_thread_handles_no_row(thread_handler_module):
    handler, _ = _build_handler(thread_handler_module, fetchone=None)

    thread_id, created = await handler.get_or_create_thread("447000000001")

    assert thread_id is None
    assert created is False


@pytest.mark.asyncio
async def test_retain_thread_executes_sql(thread_handler_module):
    handler, pool = _build_handler(thread_handler_module, fetchone={"retained": True})

    result = await handler.retain_thread("447000000001")

    assert result == {"retained": True}
    assert "retain_thread" in pool.cursor_obj.executed[0][0]


def test_handler_defaults_agent_to_project_rest_ref(thread_handler_module):
    pool = FakeAsyncPool()
    handler = thread_handler_module.ThreadHandler(pool=pool)

    # config stub builds project_settings.rest_ref = "SFCS"
    assert handler.agent == "SFCS"
