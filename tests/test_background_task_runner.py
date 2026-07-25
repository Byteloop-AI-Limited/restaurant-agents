"""
Tests for the centralized background-task runner
    . Verifies async and sync tasks run to completion
    . Verifies exceptions are logged and swallowed (response already sent)
    . Verifies CancelledError is re-raised for graceful shutdown
    . Verifies the observability counter returns to zero and reflects in-flight work
"""

import asyncio

import pytest

from restaurant_agent_core.watomation.background_task_runner import (
    get_active_background_task_count,
    run_background_task,
)


async def test_async_task_completes_and_counter_returns_to_zero():
    calls = []

    async def work(x):
        calls.append(x)

    await run_background_task("async_task", work, 5)

    assert calls == [5]
    assert await get_active_background_task_count() == 0


async def test_sync_task_completes():
    calls = []

    def work(x, y):
        calls.append((x, y))

    await run_background_task("sync_task", work, 1, y=2)

    assert calls == [(1, 2)]
    assert await get_active_background_task_count() == 0


async def test_exception_is_swallowed_and_counter_resets():
    async def boom():
        raise ValueError("kaboom")

    # Must not raise: the HTTP response has already been sent.
    await run_background_task("failing_task", boom)

    assert await get_active_background_task_count() == 0


async def test_cancelled_error_is_reraised_and_counter_resets():
    async def work():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_background_task("cancelled_task", work)

    assert await get_active_background_task_count() == 0


async def test_counter_reflects_in_flight_task():
    started = asyncio.Event()
    release = asyncio.Event()

    async def work():
        started.set()
        await release.wait()

    task = asyncio.create_task(run_background_task("in_flight_task", work))
    await started.wait()

    assert await get_active_background_task_count() == 1

    release.set()
    await task

    assert await get_active_background_task_count() == 0
