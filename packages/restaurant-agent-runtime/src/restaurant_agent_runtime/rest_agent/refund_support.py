"""Deterministic customer replies for refund-timing questions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    DELIVERY_TIMEOUT_PENDING_MESSAGE,
    REFUND_TIMING_MESSAGE,
)

_REFUND_QUERY = re.compile(
    r"\b(?:refund(?:s|ed|ing)?|money\s+back|"
    r"(?:money|payment).{0,80}\b(?:back|return(?:ed|ing)?))\b",
    re.IGNORECASE,
)

_UNCONFIRMED_REFUND_MESSAGE = (
    "I can’t confirm that a refund has been issued for this order."
)


def is_refund_timing_query(text: str | None) -> bool:
    """Recognise refund status/timing requests before they reach the model."""
    return bool(_REFUND_QUERY.search(text or ""))


def refund_reply_for_state(state: Mapping[str, Any]) -> str:
    """Return the only allowed reply for the current authoritative state."""
    if state.get("is_payment_cancelled") is True:
        return REFUND_TIMING_MESSAGE
    if state.get("is_delivery_no_rider") is True:
        return DELIVERY_TIMEOUT_PENDING_MESSAGE
    if state.get("active_agent") == "delivery_agent":
        if state.get("is_delivery_picked_up") is True:
            return "Your delivery order is still in progress. The rider has picked up your order."
        if state.get("is_delivery_rider_assigned") is True:
            return (
                "Your delivery order is still in progress and a delivery driver "
                "has been assigned."
            )
        if state.get("retain_thread") is True:
            return (
                "Your delivery order is still in progress. We are still looking "
                "for a delivery driver."
            )
    return _UNCONFIRMED_REFUND_MESSAGE


def refund_state_unavailable_reply() -> str:
    """Return the safe failure response when the checkpoint cannot be read."""
    return _UNCONFIRMED_REFUND_MESSAGE
