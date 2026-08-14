"""Tests for state-aware system-prompt instructions."""

import pytest

from restaurant_agent_runtime.rest_agent.prompt_runtime import (
    _retention_system_instruction,
)


@pytest.mark.parametrize(
    ("active_agent", "expected_flow"),
    [
        ("delivery_agent", "Delivery flow is in motion."),
        ("takeaway_agent", "Takeaway flow is in motion."),
    ],
)
def test_retained_specialist_flow_is_a_strict_no_handover_instruction(
    active_agent, expected_flow
):
    instruction = _retention_system_instruction(
        {"active_agent": active_agent, "retain_thread": True}
    )

    assert expected_flow in instruction
    assert "Strictly avoid handover to other agents." in instruction


def test_paid_retained_delivery_injects_current_order_and_rider_pending_facts():
    instruction = _retention_system_instruction(
        {
            "active_agent": "delivery_agent",
            "retain_thread": True,
            "is_payment_successful": True,
            "is_delivery_rider_assigned": False,
            "is_delivery_picked_up": False,
        }
    )

    assert "payment confirmed" in instruction
    assert "allocation is pending" in instruction
    assert "Do not ask the customer to place another order" in instruction


def test_released_specialist_flow_allows_but_does_not_require_a_transfer():
    instruction = _retention_system_instruction(
        {"active_agent": "delivery_agent", "retain_thread": False}
    )

    assert "Transfers are allowed when the customer's intent requires one" in instruction
    assert "do not hand over merely because retention has been cleared" in instruction


def test_released_thread_informs_triage_that_handoffs_are_allowed():
    instruction = _retention_system_instruction(
        {"active_agent": "triage_agent", "retain_thread": False}
    )

    assert "SPECIALIST RETENTION RELEASED" in instruction
    assert "Transfers are allowed" in instruction


def test_missing_legacy_retention_does_not_inject_a_release_instruction():
    assert _retention_system_instruction({"active_agent": "delivery_agent"}) == ""
