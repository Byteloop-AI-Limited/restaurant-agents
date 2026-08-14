"""Tests for deterministic, state-gated refund support replies."""

from restaurant_agent_runtime.rest_agent.refund_support import (
    is_refund_timing_query,
    refund_reply_for_state,
    refund_state_unavailable_reply,
)
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    DELIVERY_TIMEOUT_PENDING_MESSAGE,
    REFUND_TIMING_MESSAGE,
)


def test_recognises_refund_timing_questions():
    assert is_refund_timing_query("how long does refund takes?")
    assert is_refund_timing_query("when will my money be back?")
    assert is_refund_timing_query("how long until my money is returned?")
    assert not is_refund_timing_query("when will my food arrive?")


def test_refund_issued_is_only_confirmed_after_payment_cancellation():
    assert refund_reply_for_state({"is_payment_cancelled": True}) == REFUND_TIMING_MESSAGE


def test_active_delivery_with_assigned_rider_never_claims_refund():
    reply = refund_reply_for_state(
        {
            "active_agent": "delivery_agent",
            "retain_thread": True,
            "is_payment_cancelled": False,
            "is_delivery_rider_assigned": True,
        }
    )

    assert reply == (
        "Your delivery order is still in progress and a delivery driver has been assigned."
    )
    assert "refund has been issued" not in reply.lower()


def test_no_rider_without_confirmed_cancellation_never_claims_refund():
    assert refund_reply_for_state(
        {"is_delivery_no_rider": True, "is_payment_cancelled": False}
    ) == DELIVERY_TIMEOUT_PENDING_MESSAGE


def test_missing_state_fails_closed():
    assert refund_reply_for_state({}) == refund_state_unavailable_reply()
