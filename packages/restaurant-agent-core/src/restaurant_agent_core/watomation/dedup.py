"""
Webhook deduplication decorator.

Meta sometimes delivers the same webhook from multiple edge servers
simultaneously. This decorator drops duplicate invocations based on the
message/callback `.id` within a short TTL window.

Usage:
    @wa_dedup
    async def handle_wa_msg_in_graph(wa: WhatsApp, msg: Message):
        ...

    @wa_dedup
    async def delivery_address_confirmation(wa: WhatsApp, callback: CallbackButton):
        ...
"""

import functools
import time

from restaurant_agent_core.config import logger

_seen_ids: dict[str, float] = {}
_DEDUP_TTL_SECONDS = 30


def _check_and_record(update_id: str) -> bool:
    """Return True if this update_id is a duplicate within the TTL window."""
    now = time.monotonic()

    if len(_seen_ids) > 200:
        expired = [k for k, t in _seen_ids.items() if now - t > _DEDUP_TTL_SECONDS]
        for k in expired:
            del _seen_ids[k]

    if update_id in _seen_ids and now - _seen_ids[update_id] < _DEDUP_TTL_SECONDS:
        return True
    _seen_ids[update_id] = now
    return False


def wa_dedup(fn):
    """Decorator that drops duplicate webhook invocations by update `.id`."""

    @functools.wraps(fn)
    async def wrapper(wa, update, *args, **kwargs):
        if _check_and_record(update.id):
            logger.debug(f"Duplicate webhook dropped for id={update.id} in {fn.__name__}")
            return
        return await fn(wa, update, *args, **kwargs)

    return wrapper
