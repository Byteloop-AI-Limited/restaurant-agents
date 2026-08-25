"""Lifecycle policy for retained delivery and takeaway specialist work.

This module is the single owner of the AgentState projection for an in-flight
specialist flow.  FoodOrder and fulfilment systems remain authoritative; this
code only keeps the conversation projection coherent after those systems emit
an event.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import GraphAdapter

SpecialistAgent = Literal["delivery_agent", "takeaway_agent"]
ServiceKind = Literal["delivery", "takeaway"]

DELIVERY_PAYMENT_PENDING_RIDER_MESSAGE = (
    "Your order has been received and payment confirmed. We’re now finding a "
    "delivery driver and will let you know as soon as one is assigned."
)
NO_RIDER_REFUND_ISSUED_MESSAGE = (
    "We’re sorry, we couldn’t find a delivery driver for your order. Your refund "
    "has been issued and may take a few hours to a couple of days to appear, "
    "depending on your bank. You can still place a takeaway order if you’d like."
)
NO_RIDER_OUTCOME_PENDING_MESSAGE = (
    "We couldn’t find a delivery driver for your order. We’ll update you shortly."
)
REFUND_TIMING_MESSAGE = (
    "Your refund has been issued. It may take a few hours to a couple of days "
    "to appear, depending on your bank."
)
DELIVERY_ARRIVAL_TIME_QUALIFIER = (
    "Delivery time depends on traffic and the distance to your address."
)
DELIVERY_TIMEOUT_PENDING_MESSAGE = (
    "We couldn’t find a delivery driver for your order. We’ll update you shortly."
)
RIDER_LOCATION_PENDING_MESSAGE = (
    "We will share the rider’s location with you once it’s available."
)
RIDER_LOCATION_REQUESTED_MESSAGE = (
    "I have asked the rider to share their current location. I will send it "
    "here when they respond."
)
RIDER_LOCATION_DELIVERY_INACTIVE_MESSAGE = (
    "This delivery is no longer active, so we will not be contacting the rider."
)
RIDER_LOCATION_UNAVAILABLE_MESSAGE = (
    "We could not request the rider's location right now. Please try again shortly."
)
RIDER_LOCATION_NO_ORDER_MESSAGE = (
    "You do not have an active delivery order for us to locate."
)


@dataclass(frozen=True, slots=True)
class SpecialistFlowView:
    """The lifecycle interpretation of the persisted graph state."""

    active_agent: str | None
    retained: bool
    retention_known: bool
    is_payment_successful: bool
    is_delivery_rider_assigned: bool
    is_delivery_picked_up: bool

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "SpecialistFlowView":
        active_agent = state.get("active_agent")
        return cls(
            active_agent=active_agent if isinstance(active_agent, str) else None,
            retained=state.get("retain_thread") is True,
            retention_known="retain_thread" in state,
            is_payment_successful=state.get("is_payment_successful") is True,
            is_delivery_rider_assigned=state.get("is_delivery_rider_assigned") is True,
            is_delivery_picked_up=state.get("is_delivery_picked_up") is True,
        )

    @property
    def owns_specialist_work(self) -> bool:
        # A missing/legacy owner must not turn an explicitly retained checkpoint
        # into a handoff permission.
        return self.retained

    @property
    def handoff_allowed(self) -> bool:
        return not self.owns_specialist_work

    def system_instruction(self) -> str:
        if self.owns_specialist_work:
            flow_name = {
                "delivery_agent": "Delivery",
                "takeaway_agent": "Takeaway",
            }.get(self.active_agent, "Retained order")
            instruction = (
                "\n\nSYSTEM INSTRUCTION — RETAINED SPECIALIST FLOW:\n"
                f"{flow_name} flow is in motion. The current specialist owns this "
                "conversation. Strictly avoid handover to other agents. Handle safe "
                "customer support here, and use authoritative system-provided updates "
                "only; do not invent order or fulfilment facts. Do not call a menu tool "
                "or start another order while this flow is retained."
            )
            if self.active_agent == "delivery_agent" and self.is_payment_successful:
                return (
                    instruction
                    + " The customer’s current delivery order has been received and "
                    "payment confirmed. "
                    + _delivery_progress_instruction(self)
                    + " Do not ask the customer to place another order, select menu "
                    "items, or make payment again."
                )
            return instruction
        if self.retention_known and not self.retained:
            return (
                "\n\nSYSTEM INSTRUCTION — SPECIALIST RETENTION RELEASED:\n"
                "No retained specialist flow is active. Transfers are allowed when "
                "the customer's intent requires one, but do not hand over merely "
                "because retention has been cleared."
            )
        return ""


def _delivery_progress_instruction(view: SpecialistFlowView) -> str:
    """Return the authoritative delivery phase derived from persisted state."""
    # This helper is intentionally small: the surrounding caller has already
    # established retained delivery ownership and should not infer extra facts.
    if view.is_delivery_picked_up:
        return "The rider has picked up the order."
    if view.is_delivery_rider_assigned:
        return "A delivery driver has been assigned."
    return "A delivery driver has not yet been assigned and allocation is pending."


def specialist_agent_for(service: ServiceKind) -> SpecialistAgent:
    return "delivery_agent" if service == "delivery" else "takeaway_agent"


def retained_completion_first_message(state: Mapping[str, Any]) -> str:
    """Return the deterministic reply for a blocked retained-order handoff."""
    active_agent = SpecialistFlowView.from_state(state).active_agent
    order_label = "collection" if active_agent == "takeaway_agent" else "delivery"
    return (
        f"Of course — we just need to complete your current {order_label} order first. "
        "Once it’s finished, I’ll be happy to help with that."
    )


def retained_specialist_state(
    service: ServiceKind,
    *,
    order_id: str,
    order_number: str,
    reply_to_msg_id: str | None,
) -> dict[str, Any]:
    """Return the canonical state projection when payment starts fulfilment."""
    return {
        "active_agent": specialist_agent_for(service),
        "order_id": order_id,
        "order_number": order_number,
        "reply_to_msg_id": reply_to_msg_id,
        "is_payment_successful": True,
        "retain_thread": True,
        "is_delivery_rider_assigned": False,
        "is_delivery_picked_up": False,
        "rider_live_location_url": None,
        "is_payment_cancelled": False,
        "is_delivery_no_rider": False,
    }


def released_specialist_state() -> dict[str, Any]:
    """Return the profile-only baseline after a specialist flow has ended.

    Deliberately does not reset `selected_rest_ref`: a completed order must
    not make a multi-restaurant app re-ask which restaurant the customer
    meant. Do not add it to this dict.
    """
    return {
        "active_agent": "triage_agent",
        "retain_thread": False,
        "order_id": None,
        "order_number": None,
        "reply_to_msg_id": None,
        # Legacy checkpoints can contain these formerly implicit takeaway keys.
        "order_summary": None,
        "payment_link": None,
        "is_payment_successful": False,
        "is_delivery_rider_assigned": False,
        "rider_live_location_url": None,
        "is_delivery_picked_up": False,
        "is_payment_cancelled": False,
        "is_delivery_no_rider": False,
        "is_delivery_address_confirmed": False,
        "is_outside_delivery_area": False,
        "min_order_value": None,
    }


def new_specialist_flow_state(
    service: ServiceKind, *, rest_ref: str | None = None
) -> dict[str, Any]:
    """Start a clean non-retained order flow, retaining only profile context."""
    values = released_specialist_state()
    values["active_agent"] = specialist_agent_for(service)
    if rest_ref:
        values["rest_ref"] = rest_ref
    return values


async def notify_release_and_optionally_terminate(
    *,
    recipient: str,
    specialist: SpecialistAgent,
    message: str,
    graph_adapter: GraphAdapter,
    terminate: bool,
    release_state_overrides: Mapping[str, Any] | None = None,
) -> None:
    """Notify from a specialist, always release state, then optionally terminate.

    A terminal webhook is authoritative even when the customer notification
    fails.  The release is therefore performed in ``finally`` and a notification
    error is re-raised after required cleanup/termination work is attempted.
    """
    notification_error: Exception | None = None
    try:
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            system_msg=(
                "AUTHORITATIVE SPECIALIST LIFECYCLE EVENT: do not call a menu tool, "
                "start a new order, or hand off. Call `update_customer` with "
                f"message={message!r}. Then end this turn."
            ),
            state_update_dict={"active_agent": specialist, "retain_thread": True},
        )
    except Exception as exc:  # cleanup must still reflect the external event
        notification_error = exc
        logger.exception("Specialist terminal update failed for recipient {}", recipient)
    finally:
        release_state = released_specialist_state()
        if release_state_overrides:
            release_state.update(release_state_overrides)
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            state_update_dict=release_state,
            persist_only=True,
        )

    if terminate:
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            system_msg=(
                "AUTHORITATIVE TERMINAL EVENT: call `terminate_conversation` to end "
                "the conversation. Do not transfer, start an order, or call a menu tool."
            ),
            state_update_dict={"active_agent": "triage_agent", "retain_thread": False},
        )

    if notification_error is not None:
        raise notification_error
