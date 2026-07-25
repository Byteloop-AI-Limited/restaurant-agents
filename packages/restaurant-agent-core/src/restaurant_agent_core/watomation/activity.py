"""
Activity accounting for external stop schedulers.
  . Counts in-flight HTTP requests, background jobs, and agent runs
  . Tracks the monotonic timestamp of the last completed unit of work
  . Exposes a snapshot payload consumed by GET /internal/activity
  . Logs agent runs at INFO; requests and jobs at DEBUG to keep the default quiet
  . Makes no shutdown decisions - an external poller owns that policy
  . Single-worker design: gunicorn_conf.py asserts WEB_CONCURRENCY=1, so one
    event loop owns this state and plain integer updates need no lock
  Functions/Classes:
    . track - Async context manager counting one unit of work
    . tracked - Decorator form of track for coroutine functions
    . snapshot - Current counters, idle_seconds, and safe_to_stop
    . reset - Clear all state (tests only)
    . ActivityMiddleware - Pure ASGI middleware counting in-flight requests
"""

from __future__ import annotations

import functools
import inspect
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger

# Work kinds tracked independently. A single webhook deliberately shows up under
# more than one kind (see docs/webhook_endpoints.md) - that redundancy is the
# safety property. Consumers should test "every counter is zero", never sum them.
REQUESTS = "requests"
JOBS = "jobs"
AGENT_RUNS = "agent_runs"

# Paths excluded from request tracking. /healthz is polled by the Fly health
# check every 15s and /internal/activity by the stop scheduler; counting either
# would pin idle_seconds near zero and the machine could never be stopped.
UNTRACKED_PATHS = frozenset({"/healthz", "/internal/activity"})

# Per-kind log level. Agent runs stay at INFO because they are the unit worth
# investigating; requests and jobs are DEBUG to keep the default log quiet.
# Jobs are still logged at INFO by run_background_task, with a task_id and
# duration, so nothing is lost at the default level.
_LOG_LEVELS = {REQUESTS: "DEBUG", JOBS: "DEBUG", AGENT_RUNS: "INFO"}

# Reported in snapshot() only, as a convenience so the threshold has one home.
# The scheduler may ignore safe_to_stop and apply its own threshold to idle_seconds.
IDLE_THRESHOLD_SECONDS = float(os.getenv("ACTIVITY_IDLE_THRESHOLD_SECONDS", "60"))

_counts: dict[str, int] = {REQUESTS: 0, JOBS: 0, AGENT_RUNS: 0}
_last_activity_at: float = time.monotonic()


def reset() -> None:
    """Clear all counters and restart the idle clock. For tests only."""
    global _last_activity_at

    for kind in _counts:
        _counts[kind] = 0
    _last_activity_at = time.monotonic()


def idle_seconds() -> float:
    """Seconds since the last unit of work completed."""
    return time.monotonic() - _last_activity_at


def is_quiet() -> bool:
    """True when no request, job, or agent run is in flight."""
    return not any(_counts.values())


def safe_to_stop() -> bool:
    """True when nothing is in flight and the app has been idle long enough."""
    return is_quiet() and idle_seconds() >= IDLE_THRESHOLD_SECONDS


def snapshot() -> dict[str, Any]:
    """Payload for GET /internal/activity."""
    return {
        "active_requests": _counts[REQUESTS],
        "active_jobs": _counts[JOBS],
        "active_agent_runs": _counts[AGENT_RUNS],
        "idle_seconds": round(idle_seconds(), 3),
        # This application never refuses work: a request arriving at any moment,
        # including mid-stop, is handled. Reported for payload compatibility only.
        "draining": False,
        "safe_to_stop": safe_to_stop(),
        "idle_threshold_seconds": IDLE_THRESHOLD_SECONDS,
    }


@asynccontextmanager
async def track(kind: str, label: str):
    """Count one unit of work of `kind` for the duration of the block.

    Decrements and stamps the idle clock on every exit path, so a failed or
    cancelled unit of work cannot leak a permanently elevated counter.
    """
    global _last_activity_at

    _counts[kind] += 1
    started = time.monotonic()
    level = _LOG_LEVELS.get(kind, "DEBUG")
    work_logger = logger.bind(activity_kind=kind, activity_label=label)
    work_logger.log(level, f"Activity started: {kind} {label} (counts={_counts})")

    try:
        yield
    finally:
        _counts[kind] -= 1
        _last_activity_at = time.monotonic()
        duration_seconds = round(_last_activity_at - started, 3)
        work_logger.log(
            level,
            f"Activity finished: {kind} {label} in {duration_seconds} seconds "
            f"(counts={_counts})",
        )


def tracked(
    kind: str, label_arg: str = "recipient"
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorate a coroutine function so its whole run counts as one unit of work.

    `label_arg` names the parameter used as the log label. Callers pass it either
    positionally or by keyword, so it is resolved through the real signature.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with track(kind, _resolve_label(signature, label_arg, args, kwargs)):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def _resolve_label(
    signature: inspect.Signature,
    label_arg: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Best-effort label lookup that never breaks the wrapped call."""
    try:
        bound = signature.bind_partial(*args, **kwargs)
        return str(bound.arguments.get(label_arg, ""))
    except TypeError:
        # Let the wrapped function raise the real signature error.
        return str(kwargs.get(label_arg, args[0] if args else ""))


class ActivityMiddleware:
    """Count in-flight HTTP requests at the ASGI layer.

    Deliberately a pure ASGI middleware rather than BaseHTTPMiddleware. Starlette
    runs a response's BackgroundTasks inside `Response.__call__`, which is inside
    `await self.app(...)`, so a request stays counted until its background tasks
    finish too. BaseHTTPMiddleware returns from call_next before that happens and
    would report the request as complete while the job was still running.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") in UNTRACKED_PATHS:
            await self.app(scope, receive, send)
            return

        async with track(REQUESTS, scope.get("path", "")):
            await self.app(scope, receive, send)
