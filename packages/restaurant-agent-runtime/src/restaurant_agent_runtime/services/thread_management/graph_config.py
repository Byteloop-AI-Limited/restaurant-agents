"""Build LangGraph configuration from persisted Restaurant Threads."""

from typing import Any

from loguru import logger
from psycopg_pool import AsyncConnectionPool

from .thread_handler import ThreadHandler


async def get_config_for_recipient(
    recipient: str,
    pool: AsyncConnectionPool,
    *,
    agent: str,
    force_new_thread: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Resolve one recipient to its Restaurant-scoped persisted Thread."""

    thread_handler = ThreadHandler(pool, agent=agent)
    if force_new_thread:
        await thread_handler.make_threads_inactive(recipient)
        logger.info("Made threads inactive for recipient {}", recipient)

    thread_id, is_new_thread = await thread_handler.get_or_create_thread(recipient)
    config = {"configurable": {"thread_id": thread_id, "recipient": recipient}}
    return config, is_new_thread

