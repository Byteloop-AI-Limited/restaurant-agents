"""
Centralized runner for FastAPI/Starlette background tasks.
  . Wraps fire-and-forget background tasks with structured start/complete/failure logs
  . Assigns each task a name and a unique id, and measures duration
  . Swallows exceptions (the HTTP response has already been sent) but logs them
  . Re-raises CancelledError so graceful shutdown proceeds correctly
  . Registers each task with watomation.activity so GET /internal/activity reports it
  Functions/Classes:
    . run_background_task - Run and observe a single background task
    . get_active_background_task_count - Current number of in-flight tasks
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger

from restaurant_agent_runtime.watomation import activity


async def get_active_background_task_count() -> int:
    return activity.snapshot()["active_jobs"]


async def run_background_task(
    task_name: str,
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Run and observe a FastAPI/Starlette background task.

    Exceptions are logged and swallowed because the HTTP response has already
    been sent. Cancellation is logged and re-raised so graceful shutdown can
    proceed correctly.
    """
    task_id = uuid.uuid4().hex
    started = time.monotonic()
    task_logger = logger.bind(task_id=task_id, task_name=task_name)

    task_logger.info("Background task started")

    async with activity.track(activity.JOBS, task_name):
        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            task_logger.warning("Background task cancelled during shutdown")
            raise
        except Exception:
            task_logger.exception("Background task failed")
        else:
            duration_seconds = round(time.monotonic() - started, 3)
            task_logger.info(
                "Background task completed in {} seconds",
                duration_seconds,
            )
