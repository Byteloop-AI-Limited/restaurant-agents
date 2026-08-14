from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    DELIVERY_PAYMENT_PENDING_RIDER_MESSAGE,
    SpecialistFlowView,
    new_specialist_flow_state,
    notify_release_and_optionally_terminate,
    retained_completion_first_message,
    retained_specialist_state,
    released_specialist_state,
)


def test_release_clears_order_scoped_state_but_preserves_profile_by_omission():
    values = released_specialist_state()

    assert values["active_agent"] == "triage_agent"
    assert values["retain_thread"] is False
    assert values["order_id"] is None
    assert values["is_payment_successful"] is False
    assert values["is_payment_cancelled"] is False
    assert values["is_delivery_no_rider"] is False
    assert values["is_delivery_address_confirmed"] is False
    assert "customer_address" not in values
    assert "wa_name" not in values
    assert "ask_for_consent" not in values


def test_new_service_selection_starts_from_the_profile_only_baseline():
    values = new_specialist_flow_state("takeaway", rest_ref="sfcs")

    assert values["active_agent"] == "takeaway_agent"
    assert values["retain_thread"] is False
    assert values["rest_ref"] == "sfcs"
    assert values["order_number"] is None


def test_retained_state_is_fail_closed_even_without_a_specialist_owner():
    assert SpecialistFlowView.from_state({"retain_thread": True}).owns_specialist_work


def test_paid_delivery_state_resets_stale_rider_facts_and_explains_pending_allocation():
    state = retained_specialist_state(
        "delivery", order_id="ORD-1", order_number="SFCS-1", reply_to_msg_id="wamid"
    )

    assert state["is_delivery_rider_assigned"] is False
    assert state["is_delivery_picked_up"] is False
    assert state["rider_live_location_url"] is None
    assert state["is_payment_cancelled"] is False
    assert state["is_delivery_no_rider"] is False
    assert DELIVERY_PAYMENT_PENDING_RIDER_MESSAGE.startswith("Your order has been received")
    assert "allocation is pending" in SpecialistFlowView.from_state(state).system_instruction()


def test_completion_first_reply_uses_the_retained_service_name():
    assert "current delivery order" in retained_completion_first_message(
        {"active_agent": "delivery_agent", "retain_thread": True}
    )
    assert "current collection order" in retained_completion_first_message(
        {"active_agent": "takeaway_agent", "retain_thread": True}
    )


@pytest.mark.asyncio
async def test_terminal_release_persists_even_when_customer_notification_fails():
    graph_adapter = SimpleNamespace(
        run_rest_graph_with_custom_msg=AsyncMock(
            side_effect=[RuntimeError("send failed"), None]
        )
    )

    with pytest.raises(RuntimeError, match="send failed"):
        await notify_release_and_optionally_terminate(
            recipient="447000000001",
            specialist="delivery_agent",
            message="No rider available.",
            graph_adapter=graph_adapter,
            terminate=False,
        )

    assert graph_adapter.run_rest_graph_with_custom_msg.await_count == 2
    release = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[1].kwargs
    assert release["persist_only"] is True
    assert release["state_update_dict"] == released_specialist_state()


@pytest.mark.asyncio
async def test_terminal_completion_releases_before_triage_termination():
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())

    await notify_release_and_optionally_terminate(
        recipient="447000000001",
        specialist="takeaway_agent",
        message="Ready shortly.",
        graph_adapter=graph_adapter,
        terminate=True,
    )

    calls = graph_adapter.run_rest_graph_with_custom_msg.await_args_list
    assert calls[0].kwargs["state_update_dict"] == {
        "active_agent": "takeaway_agent",
        "retain_thread": True,
    }
    assert calls[1].kwargs["state_update_dict"] == released_specialist_state()
    assert calls[2].kwargs["state_update_dict"] == {
        "active_agent": "triage_agent",
        "retain_thread": False,
    }


@pytest.mark.asyncio
async def test_timeout_release_retains_the_verified_payment_cancellation_projection():
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())

    await notify_release_and_optionally_terminate(
        recipient="447000000001",
        specialist="delivery_agent",
        message="No rider found.",
        graph_adapter=graph_adapter,
        terminate=False,
        release_state_overrides={
            "is_payment_cancelled": True,
            "is_delivery_no_rider": True,
        },
    )

    release = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[1].kwargs
    assert release["state_update_dict"]["is_payment_cancelled"] is True
    assert release["state_update_dict"]["is_delivery_no_rider"] is True
