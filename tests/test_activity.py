"""
Tests for activity accounting consumed by GET /internal/activity
  . Verifies counter increment/decrement across success, failure, and cancellation
  . Verifies the tracked() decorator preserves identity and resolves labels
  . Verifies UNTRACKED_PATHS leaves counters and the idle clock alone
  . Verifies an eagerly-returned response keeps its background task counted
"""

import ast
import asyncio
import pathlib
import time

import pytest
from fastapi import BackgroundTasks, FastAPI
from loguru import logger
from starlette.testclient import TestClient

from restaurant_agent_runtime.watomation import activity
from restaurant_agent_runtime.watomation.activity import ActivityMiddleware
from restaurant_agent_runtime.watomation.background_task_runner import (
    get_active_background_task_count,
    run_background_task,
)


@pytest.fixture(autouse=True)
def reset_activity():
    """Module state is shared with tests/test_background_task_runner.py."""
    activity.reset()
    yield
    activity.reset()


# %% Counters


async def test_track_counts_then_releases():
    async with activity.track(activity.JOBS, "job-1"):
        assert activity.snapshot()["active_jobs"] == 1
        assert not activity.is_quiet()

    assert activity.snapshot()["active_jobs"] == 0
    assert activity.is_quiet()


async def test_track_releases_on_exception():
    with pytest.raises(RuntimeError):
        async with activity.track(activity.JOBS, "boom"):
            raise RuntimeError("boom")

    assert activity.snapshot()["active_jobs"] == 0


async def test_track_releases_on_cancellation():
    started = asyncio.Event()

    async def work():
        async with activity.track(activity.JOBS, "cancelled"):
            started.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(work())
    await started.wait()
    assert activity.snapshot()["active_jobs"] == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert activity.snapshot()["active_jobs"] == 0


async def test_kinds_are_counted_independently():
    async with activity.track(activity.JOBS, "j"):
        async with activity.track(activity.AGENT_RUNS, "a"):
            snapshot = activity.snapshot()

    assert snapshot["active_jobs"] == 1
    assert snapshot["active_agent_runs"] == 1
    assert snapshot["active_requests"] == 0


# %% safe_to_stop


async def test_safe_to_stop_false_while_work_in_flight(monkeypatch):
    monkeypatch.setattr(activity, "IDLE_THRESHOLD_SECONDS", 0.0)

    async with activity.track(activity.JOBS, "j"):
        assert activity.safe_to_stop() is False

    assert activity.safe_to_stop() is True


async def test_safe_to_stop_false_before_idle_threshold(monkeypatch):
    monkeypatch.setattr(activity, "IDLE_THRESHOLD_SECONDS", 3600.0)

    assert activity.is_quiet() is True
    assert activity.safe_to_stop() is False


async def test_snapshot_never_reports_draining():
    assert activity.snapshot()["draining"] is False


# %% Log levels


def test_only_agent_runs_log_at_info():
    """Requests and jobs at DEBUG keeps the default log quiet on a 1GB machine.

    Promoting requests back to INFO costs ~27us and ~1.7KB of JSON per request,
    so this mapping is deliberate rather than incidental.
    """
    assert activity._LOG_LEVELS[activity.AGENT_RUNS] == "INFO"
    assert activity._LOG_LEVELS[activity.REQUESTS] == "DEBUG"
    assert activity._LOG_LEVELS[activity.JOBS] == "DEBUG"


async def test_track_emits_at_the_kind_s_level():
    records = []
    sink_id = logger.add(
        lambda message: records.append(message.record), level="DEBUG"
    )
    try:
        async with activity.track(activity.AGENT_RUNS, "447000000001"):
            pass
        async with activity.track(activity.REQUESTS, "/"):
            pass
    finally:
        logger.remove(sink_id)

    levels = {
        record["extra"]["activity_kind"]: record["level"].name for record in records
    }
    assert levels == {activity.AGENT_RUNS: "INFO", activity.REQUESTS: "DEBUG"}


# %% tracked() decorator


async def test_tracked_decorator_counts_and_preserves_identity():
    seen = []

    @activity.tracked(activity.AGENT_RUNS, label_arg="recipient")
    async def run(recipient: str, extra: str = "x"):
        seen.append(activity.snapshot())
        return f"{recipient}:{extra}"

    assert run.__name__ == "run"

    assert await run("447000000001") == "447000000001:x"
    assert await run(recipient="447000000002", extra="y") == "447000000002:y"

    assert [snapshot["active_agent_runs"] for snapshot in seen] == [1, 1]
    assert activity.snapshot()["active_agent_runs"] == 0


async def test_tracked_decorator_releases_on_exception():
    @activity.tracked(activity.AGENT_RUNS)
    async def run(recipient: str):
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await run("447000000001")

    assert activity.snapshot()["active_agent_runs"] == 0


def test_agent_runner_entrypoint_is_decorated():
    """run_rest_graph_with_custom_msg is the single choke point for agent runs.

    Checked via AST rather than by importing: the runtime runner imports settings
    whose deployment configuration is initialized at module import time.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    source = (
        repo_root
        / "packages"
        / "restaurant-agent-runtime"
        / "src"
        / "restaurant_agent_runtime"
        / "rest_agent"
        / "agent_runner.py"
    ).read_text()
    tree = ast.parse(source)

    targets = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "run_rest_graph_with_custom_msg"
    ]
    assert len(targets) == 1, "expected one shared agent-run entrypoint"

    decorators = [ast.unparse(dec) for dec in targets[0].decorator_list]
    tracking = [dec for dec in decorators if "activity.tracked" in dec]
    assert tracking, decorators
    assert any(
        "AGENT_RUNS" in dec or activity.AGENT_RUNS in dec for dec in tracking
    ), tracking
    assert any("recipient" in dec for dec in tracking), tracking


# %% background_task_runner integration


async def test_run_background_task_reports_as_a_job():
    seen = []

    async def work():
        seen.append(activity.snapshot())

    await run_background_task("job-name", work)

    assert seen[0]["active_jobs"] == 1
    assert await get_active_background_task_count() == 0


async def test_failing_background_task_still_releases():
    async def boom():
        raise RuntimeError("boom")

    await run_background_task("failing", boom)

    assert await get_active_background_task_count() == 0


# %% ASGI middleware


def _build_app() -> FastAPI:
    """Throwaway app: the real watomation.fapp import needs full AWS/Supabase env."""
    app = FastAPI()
    app.add_middleware(ActivityMiddleware)

    captured: list[dict] = []
    app.state.captured = captured

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/internal/activity")
    async def internal_activity():
        return activity.snapshot()

    @app.get("/inline")
    async def inline():
        captured.append(activity.snapshot())
        return {"ok": True}

    @app.post("/probe")
    async def probe(background_tasks: BackgroundTasks):
        async def slow_job():
            captured.append(activity.snapshot())
            await asyncio.sleep(0.05)

        background_tasks.add_task(run_background_task, "slow", slow_job)
        return {"ok": True}

    return app


def test_middleware_counts_a_tracked_request():
    app = _build_app()
    with TestClient(app) as client:
        assert client.get("/inline").status_code == 200

    assert app.state.captured[0]["active_requests"] == 1
    assert activity.snapshot()["active_requests"] == 0


def test_untracked_paths_do_not_reset_the_idle_clock():
    """Health checks and scheduler polling must never rewind idle_seconds."""
    app = _build_app()
    with TestClient(app) as client:
        activity.reset()
        time.sleep(0.05)
        before = activity.idle_seconds()

        assert client.get("/healthz").json() == {"status": "ok"}
        first = client.get("/internal/activity").json()
        second = client.get("/internal/activity").json()

        assert first["active_requests"] == 0
        assert activity.idle_seconds() >= before
        assert second["idle_seconds"] >= first["idle_seconds"] >= before


def test_tracked_path_does_reset_the_idle_clock():
    """Contrast with the untracked case: real work must rewind idle_seconds."""
    app = _build_app()
    with TestClient(app) as client:
        activity.reset()
        time.sleep(0.05)
        before = activity.idle_seconds()

        client.get("/inline")

        assert activity.idle_seconds() < before


def test_eager_response_keeps_its_background_job_counted():
    """The load-bearing claim: the ASGI call stays open through Response.background.

    Starlette runs BackgroundTasks inside Response.__call__, which is inside
    `await self.app(...)`. So the eager `return {"ok": True}` ends the handler, not
    the ASGI call, and the request stays counted for the whole job. Swapping in
    BaseHTTPMiddleware would break this and fail here.
    """
    app = _build_app()
    with TestClient(app) as client:
        response = client.post("/probe")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Captured from inside the background job, i.e. after the response was produced.
    during_job = app.state.captured[0]
    assert during_job["active_jobs"] == 1
    assert during_job["active_requests"] >= 1
    assert during_job["safe_to_stop"] is False

    assert activity.is_quiet()


def test_lifespan_scope_passes_through():
    """A non-http scope must not be counted — otherwise startup/shutdown breaks."""
    app = _build_app()
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    assert activity.snapshot()["active_requests"] == 0
