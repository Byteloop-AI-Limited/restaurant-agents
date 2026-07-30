"""
Unit tests for thread hooks router functions
    . Loads thread_hooks with stubbed config, restaurant params, runner, and thread handler dependencies
    . Tests router functions directly without a FastAPI server
    . Covers reduced stale-thread scheduling, debug endpoints, active thread lookup, and HIL routing
  Functions/Classes:
    . FakeBackgroundTasks
    . FakeThreadHandler
    . thread_module
    . test_validate_rest_ref_success_and_failure
    . test_terminate_stale_active_threads_queues_valid_batch
    . test_stale_thread_candidate_invokes_graph_and_isolates_failures
    . test_get_active_thread_found_and_missing
    . test_debug_endpoints_return_runner_values
    . test_hil_system_message_uses_explicit_or_lookup_recipient
    . test_hil_system_message_raises_404_when_thread_missing
"""

import asyncio
from types import ModuleType
from uuid import UUID

import pytest
from fastapi import HTTPException

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append({"func": func, "args": args, "kwargs": kwargs})


class FakeThreadHandler:
    active_thread = {"thread_id": "thread-active"}

    def __init__(self, pool):
        self.pool = pool

    async def get_active_thread(self, recipient):
        return self.active_thread


@pytest.fixture
def thread_module(monkeypatch):
    config_stub = build_config_stub()

    async def get_pool():
        return object()

    config_stub.pg_settings.get_pool = get_pool
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={"thread": [{"thread_id": "thread-1", "recipient": "447000000001"}]}
    )

    runner_module = ModuleType("sfcs_agent.rest_agent.agent_runner")
    runner_module.run_calls = []
    runner_module.raise_on_run = False

    async def run_rest_graph_with_custom_msg(**kwargs):
        runner_module.run_calls.append(kwargs)
        if runner_module.raise_on_run:
            raise RuntimeError("runner down")
        return "graph response"

    async def debug_state_values(*args, **kwargs):
        config = kwargs.get("config")
        if config and config["configurable"]["thread_id"] == "thread-1":
            return {"retain_thread": True}
        return {"retain_thread": False, "args": args, "kwargs": kwargs}

    async def debug_state(*args, **kwargs):
        return {"debug_state": True, "args": args, "kwargs": kwargs}

    async def debug_state_by_thread(thread_id):
        return {"thread_id": thread_id}

    runner_module.run_rest_graph_with_custom_msg = run_rest_graph_with_custom_msg
    runner_module.debug_state_values = debug_state_values
    runner_module.debug_state = debug_state
    runner_module.debug_state_by_thread = debug_state_by_thread

    thread_management_module = ModuleType("restaurant_agent_runtime.services.thread_management")
    thread_management_module.ThreadHandler = FakeThreadHandler

    module = load_module(
        "test_thread_hooks_module",
        "restaurant_agent_runtime.watomation/routers/thread_hooks.py",
        monkeypatch,
        {
            "config": config_stub,
            "sfcs_agent.rest_agent.agent_runner": runner_module,
            "restaurant_agent_runtime.services.thread_management": thread_management_module,
        },
    )
    module._runner_module = runner_module
    module._config_stub = config_stub
    return module


def test_validate_rest_ref_success_and_failure(thread_module):
    assert thread_module.validate_rest_ref("sfcs") == "SFCS"

    with pytest.raises(HTTPException) as exc:
        thread_module.validate_rest_ref("bad")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_terminate_stale_active_threads_queues_valid_batch(thread_module):
    request = thread_module.TerminateStaleThreadsRequest(
        job_run_id="12345678-1234-5678-1234-567812345678",
        threads=[
            {
                "thread_id": "SFCS-thread-1",
                "recipient": "447000000001",
            },
            {
                "thread_id": "SFCS-thread-2",
                "recipient": "447000000002",
            },
        ],
    )
    bg = FakeBackgroundTasks()

    result = await thread_module.terminate_stale_active_threads("sfcs", request, bg)

    assert result.job_run_id == request.job_run_id
    assert result.received_count == 2
    assert result.queued_count == 2
    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    if task["func"] is getattr(thread_module, "run_background_task", None):
        assert task["args"][:2] == (
            "terminate_stale_thread_batch",
            thread_module._process_stale_thread_batch,
        )
    else:
        assert task["func"] is thread_module._process_stale_thread_batch
    assert task["kwargs"] == {"rest_ref": "SFCS", "request": request}


@pytest.mark.asyncio
async def test_terminate_stale_active_threads_rejects_prefix_mismatch(thread_module):
    request = thread_module.TerminateStaleThreadsRequest(
        job_run_id="12345678-1234-5678-1234-567812345678",
        threads=[
            {
                "thread_id": "ELAS-thread-1",
                "recipient": "447000000001",
            }
        ],
    )
    bg = FakeBackgroundTasks()

    with pytest.raises(HTTPException) as exc:
        await thread_module.terminate_stale_active_threads("SFCS", request, bg)

    assert exc.value.status_code == 400
    assert bg.tasks == []


@pytest.mark.asyncio
async def test_stale_thread_candidate_invokes_graph_and_isolates_failures(
    thread_module,
):
    candidate = thread_module.StaleThreadCandidate(
        thread_id="SFCS-thread-1",
        recipient="447000000001",
    )
    semaphore = asyncio.Semaphore(1)

    await thread_module._terminate_stale_thread_candidate(
        rest_ref="SFCS",
        job_run_id=UUID("12345678-1234-5678-1234-567812345678"),
        candidate=candidate,
        semaphore=semaphore,
    )
    assert thread_module._runner_module.run_calls == [
        {
            "recipient": "447000000001",
            "config": {
                "configurable": {
                    "thread_id": "SFCS-thread-1",
                    "recipient": "447000000001",
                }
            },
            "system_msg": thread_module.STALE_THREAD_TERMINATION_SYSTEM_MSG,
        }
    ]

    thread_module._runner_module.raise_on_run = True
    await thread_module._terminate_stale_thread_candidate(
        rest_ref="SFCS",
        job_run_id=UUID("12345678-1234-5678-1234-567812345678"),
        candidate=candidate,
        semaphore=semaphore,
    )
    assert len(thread_module._runner_module.run_calls) == 2


@pytest.mark.asyncio
async def test_process_stale_thread_batch_limits_concurrency(
    thread_module, monkeypatch
):
    active = 0
    maximum_active = 0

    async def tracked_candidate(*, semaphore, **kwargs):
        nonlocal active, maximum_active
        async with semaphore:
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1

    monkeypatch.setattr(
        thread_module, "_terminate_stale_thread_candidate", tracked_candidate
    )

    async def unexpected_get_pool():
        raise AssertionError("stale-thread batch must not perform a preflight DB read")

    thread_module._config_stub.pg_settings.get_pool = unexpected_get_pool
    request = thread_module.TerminateStaleThreadsRequest(
        job_run_id="12345678-1234-5678-1234-567812345678",
        threads=[
            {
                "thread_id": f"SFCS-thread-{index}",
                "recipient": f"44700000000{index}",
            }
            for index in range(6)
        ],
    )

    await thread_module._process_stale_thread_batch(rest_ref="SFCS", request=request)

    assert maximum_active == thread_module.STALE_THREAD_TERMINATION_CONCURRENCY


@pytest.mark.asyncio
async def test_get_active_thread_found_and_missing(thread_module):
    assert await thread_module.get_active_thread("elas", "447") == {
        "thread_id": "thread-active",
        "rest_ref": "elas",
        "recipient": "447",
    }

    FakeThreadHandler.active_thread = None
    try:
        assert await thread_module.get_active_thread("elas", "447") == {
            "thread_id": "-1",
            "rest_ref": "elas",
            "recipient": "447",
        }
    finally:
        FakeThreadHandler.active_thread = {"thread_id": "thread-active"}


@pytest.mark.asyncio
async def test_debug_endpoints_return_runner_values(thread_module):
    assert await thread_module.debug_state_values_path("447") == {
        "retain_thread": False,
        "args": ("447",),
        "kwargs": {},
    }
    assert (await thread_module.debug_state_path("447"))["debug_state"] is True
    assert await thread_module.debug_thread_path("thread-1") == {
        "thread_id": "thread-1"
    }
    assert (await thread_module.debug_admin_state_path("447"))["debug_state"] is True
    assert await thread_module.debug_state_by_thread_path("thread-2") == {
        "thread_id": "thread-2"
    }


@pytest.mark.asyncio
async def test_hil_system_message_uses_explicit_or_lookup_recipient(thread_module):
    explicit = await thread_module.hil_system_message(
        thread_module.HILMessageRequest(
            thread_id="thread-1",
            recipient="447",
            update_message="Manual update",
            state_update_dict={"x": 1},
        )
    )
    assert explicit == {
        "status": "success",
        "thread_id": "thread-1",
        "recipient": "447",
        "response": "graph response",
    }
    assert thread_module._runner_module.run_calls[-1] == {
        "recipient": "447",
        "system_msg": "call tool `send_updates_to_customer` with update_to_be_sent: Manual update",
        "state_update_dict": {"x": 1},
    }

    looked_up = await thread_module.hil_system_message(
        thread_module.HILMessageRequest(
            thread_id="thread-1",
            update_message="Lookup recipient",
        )
    )
    assert looked_up["recipient"] == "447000000001"


@pytest.mark.asyncio
async def test_hil_system_message_raises_404_when_thread_missing(thread_module):
    thread_module.client_ordelo = FakeSupabaseClient(table_data={"thread": []})

    with pytest.raises(HTTPException) as exc:
        await thread_module.hil_system_message(
            thread_module.HILMessageRequest(
                thread_id="missing",
                update_message="No thread",
            )
        )
    assert exc.value.status_code == 404
