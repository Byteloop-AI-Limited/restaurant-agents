"""
WhatsApp message handlers for customer interactions
    . Processes various types of incoming WhatsApp messages
    . Manages conversation flows using LangGraph for stateful dialogues
    . Processes location data shared by customers
    . Implements thread state management for conversation history
    . Bypasses the after-hours guard for runtime Overwatch recipients
    . Defers service-hour decisions to REST_MASTER.service_hours (WeeklySchedule)
  Functions/Classes:
    . handle_wa_msg_in_graph - Routes messages to appropriate graph handler
    . handle_wa_msg_status - Logs message delivery status
    . handle_request_location_response - Processes location data from customers
    . reset_thread - Resets conversation thread for clean state
    . is_outside_service_hours - Checks if message arrived outside restaurant hours
    . send_closed_message - Sends a message when the restaurant is closed
    . send_redirect_to_offline_mode - Sends a placeholder message for offline mode
    . _message_time_uk - Converts message timestamp to UK timezone
"""

# %%
import asyncio
import json
from datetime import datetime, timezone

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from pywa.types import Message, MessageStatus
from pywa_async import WhatsApp, filters

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.maps_service import AddressResolver
from restaurant_agent_runtime.services.operational_diagnostics import (
    application_url_details,
    reset_project_application_caches,
)
from restaurant_agent_runtime.services.thread_management import ThreadHandler
from restaurant_agent_runtime.services.tz_utils import UK_TZ
from restaurant_agent_runtime.watomation.dedup import wa_dedup
from restaurant_agent_runtime.waba_callback import build_runtime_details
from restaurant_agent_runtime.rest_agent.service_selection import (
    classify_service_selection,
    route_service_selection,
)
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import SpecialistFlowView
from restaurant_agent_runtime.rest_agent.refund_support import (
    is_refund_timing_query,
    refund_reply_for_state,
    refund_state_unavailable_reply,
)
# %% After-hours guard
def _message_time_uk(msg: Message) -> datetime | None:
    ts = getattr(msg, "timestamp", None) or getattr(msg, "timestamp_ms", None)
    if ts is None:
        return None

    if isinstance(ts, datetime):
        dt_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(UK_TZ)

    try:
        ts_val = float(ts)
    except (TypeError, ValueError):
        return None

    if ts_val > 1_000_000_000_000:  # likely milliseconds
        ts_val = ts_val / 1000
    try:
        utc_time = datetime.fromtimestamp(ts_val, tz=timezone.utc)
    except (OSError, ValueError):
        return None
    return utc_time.astimezone(UK_TZ)


def is_outside_service_hours(
    _: WhatsApp, msg: Message, runtime: RestaurantRuntime
) -> bool:
    msg_time = _message_time_uk(msg)
    if msg_time is None:
        return False

    return not runtime.operational_lookups.is_open(msg.sender, msg_time)


def create_out_of_hours_filter(runtime: RestaurantRuntime):
    """Bind the filter to one restaurant instead of shared process state."""

    return filters.new(lambda wa, msg: is_outside_service_hours(wa, msg, runtime))


def create_overwatch_filter(runtime: RestaurantRuntime):
    """Bind privileged-message filtering to this runtime's cached allowlist."""

    return filters.new(
        lambda _wa, msg: runtime.operational_lookups.is_overwatch_recipient(
            msg.sender
        )
    )


_ORDERING_TERMS = (
    "delivery",
    "collection",
    "takeaway",
    "pickup",
    "pick up",
    "order",
    "menu",
)


def is_ordering_request(msg: Message) -> bool:
    """Return whether an after-hours text is an attempt to place an order."""
    text = (getattr(msg, "text", None) or "").casefold()
    return any(term in text for term in _ORDERING_TERMS)


async def send_closed_message(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
    graph_adapter: GraphAdapter | None = None,
):
    # Existing paid/in-progress work is not a new-order attempt.  This handler
    # runs before the normal graph message path, so it must not strand a
    # retained specialist after hours.
    if graph_adapter is not None:
        try:
            state = await graph_adapter.debug_state_values(recipient=msg.sender)
        except Exception:
            logger.exception(
                "Could not inspect retained state for after-hours recipient {}",
                msg.sender,
            )
            await graph_adapter.run_rest_graph_with_custom_msg(
                recipient=msg.sender,
                human_msg=msg.text,
                wa_name=msg.from_user.name,
            )
            return
        else:
            if SpecialistFlowView.from_state(state).owns_specialist_work:
                await graph_adapter.run_rest_graph_with_custom_msg(
                    recipient=msg.sender,
                    human_msg=msg.text,
                    wa_name=msg.from_user.name,
                )
                return

    if is_ordering_request(msg):
        await wa.send_message(to=msg.sender, text="Ordering is currently closed.")
        return

    schedule = runtime.operational_lookups.get_restaurant_master().service_hours
    closed_text = schedule.format_today(datetime.now(UK_TZ))
    await wa.send_message(
        to=msg.sender,
        text=f"Thank you for your message. {closed_text}",
    )


# %% redirect user to offline mode
async def send_redirect_to_offline_mode(wa: WhatsApp, msg: Message):
    await wa.send_message(
        to=msg.sender,
        text="Thank you for your message. We are going live on the *11th of December*. See you then !!!",
    )


# %% Simulate payment completion
WHEN_PAYMENT_COMPLETE = filters.contains("/paid3100", ignore_case=True)


async def simulate_payment_complete(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
):
    """Trigger the external payment-complete hook for the sender's latest order."""

    recipient = msg.sender
    database_client = runtime.settings.database_client
    ordelo_app_url = runtime.operational_lookups.get_app_url("ORDELO")
    result = (
        database_client.table("food_order")
        .select("order_id, payment_status")
        .eq("recipient", recipient)
        .order("order_dtts", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data or result.data[0].get("payment_status") != "requires_payment":
        await wa.send_message(
            to=recipient,
            text="No order requiring payment found.",
        )
        return

    order_id = result.data[0]["order_id"]
    url = f"{ordelo_app_url}/payment-hooks/payment-complete"
    payload = {"data": {"object": {"metadata": {"orderID": order_id}}}}

    async with httpx.AsyncClient(follow_redirects=False) as client:
        try:
            response = await client.post(url, json=payload)
            if response.is_redirect:
                logger.error(
                    "Unexpected redirect POSTing payment complete for {}: "
                    "{} {} -> {}",
                    order_id,
                    response.status_code,
                    url,
                    response.headers.get("location"),
                )
                return
            response.raise_for_status()
            logger.info(
                "Payment simulation success for {}: {}",
                order_id,
                response.json(),
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error simulating payment for {} at {}: {} - {}",
                order_id,
                exc.request.url,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:
            logger.error("Error simulating payment for {}: {}", order_id, exc)


# %% Handle text in graph
@wa_dedup
async def handle_wa_msg_in_graph(
    wa: WhatsApp,
    msg: Message,
    *,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
):
    await msg.indicate_typing()
    human_msg = msg.text
    wa_name: str = msg.from_user.name

    if is_refund_timing_query(human_msg):
        try:
            state = await graph_adapter.debug_state_values(recipient=msg.sender)
        except Exception:
            logger.exception(
                "Could not read refund state for recipient {}; failing closed",
                msg.sender,
            )
            reply = refund_state_unavailable_reply()
        else:
            reply = refund_reply_for_state(state)

        try:
            await graph_adapter.run_rest_graph_with_custom_msg(
                recipient=msg.sender,
                msgs=[HumanMessage(human_msg), AIMessage(reply)],
                persist_only=True,
            )
        except Exception:
            # The direct response stays deterministic even if the transcript
            # cannot be persisted. Never send the refund query to the model.
            logger.exception(
                "Could not persist refund reply for recipient {}", msg.sender
            )
        await runtime.async_wa_client.send_message(to=msg.sender, text=reply)
        return

    service = classify_service_selection(human_msg)
    if service is not None:
        await route_service_selection(
            recipient=msg.sender,
            service=service,
            human_msg=human_msg,
            graph_adapter=graph_adapter,
            runtime=runtime,
        )
        return

    await graph_adapter.run_rest_graph_with_custom_msg(
        human_msg=human_msg, recipient=msg.sender, wa_name=wa_name, wa_msg_id=msg.id
    )


# %%
async def handle_wa_msg_status(wa: WhatsApp, msg: MessageStatus):
    logger.info(f"Message status: {msg}")


# %% Handle location
async def handle_request_location_response(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
):
    location = msg.location
    address = AddressResolver(
        runtime.settings.maps.maps_api_key
    ).get_address_from_coordinates(
        location.latitude, location.longitude
    )
    logger.info(f"Address: {address}")


# %% On reset
WHEN_RESET = filters.matches("/reset", ignore_case=True)


@wa_dedup
async def reset_thread(
    wa: WhatsApp, msg: Message, *, runtime: RestaurantRuntime
):
    logger.info("=============== reset the thread ===============")
    recipient = msg.from_user.wa_id

    if not runtime.operational_lookups.is_overwatch_recipient(recipient):
        await wa.send_message(
            to=recipient,
            text="Reset is not available. Please continue in this conversation.",
        )
        return

    pool = await runtime.settings.database.get_pool()
    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    await thread_handler.make_threads_inactive(recipient=recipient)
    await wa.send_message(to=recipient, text="Starting new conversation")


# %% Debug state
WHEN_DEBUG = filters.matches("/debug", ignore_case=True)
WHEN_DETAIL = filters.matches("/detail", ignore_case=True)
WHEN_RESET_CACHE = filters.matches("/reset-cache", ignore_case=True)


def _format_debug_state(state: dict) -> str:
    lines = ["*Debug State*"]
    for key, value in state.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _format_application_urls(app_urls: dict[str, str | None]) -> str:
    lines = ["*App URLs*"]
    for key, value in app_urls.items():
        lines.append(f"{key}: {value or 'unavailable'}")
    return "\n".join(lines)


def _format_cache_reset_outcomes(outcomes: dict[str, str]) -> str:
    labels = {
        "reset": "reset",
        "unavailable": "URL unavailable",
        "invalid_url": "invalid URL",
        "failed": "reset failed",
    }
    lines = ["*Cache Reset*"]
    for app_ref, outcome in outcomes.items():
        lines.append(f"{app_ref}: {labels[outcome]}")
    return "\n".join(lines)


async def handle_debug_state(
    wa: WhatsApp,
    msg: Message,
    *,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
):
    recipient = msg.sender
    if not runtime.operational_lookups.is_overwatch_recipient(recipient):
        return
    try:
        state = await graph_adapter.debug_state(recipient)
        text = _format_debug_state(state)
    except Exception as e:
        logger.error(f"Error fetching debug state for {recipient}: {e}")
        text = f"Error fetching debug state: {e}"
    app_urls, _ = await asyncio.to_thread(
        application_url_details,
        runtime.operational_lookups,
    )
    await wa.send_message(
        to=recipient,
        text=f"{text}\n\n{_format_application_urls(app_urls)}",
    )


async def handle_runtime_details(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
):
    """Send the same sanitized runtime details exposed by ``GET /details``."""
    recipient = msg.sender
    if not runtime.operational_lookups.is_overwatch_recipient(recipient):
        return
    details = await build_runtime_details(runtime)
    await wa.send_message(to=recipient, text=json.dumps(details, indent=2, default=str))


@wa_dedup
async def reset_project_cache(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
):
    """Force-refresh configured app URLs and reset every app's local cache."""
    recipient = msg.sender
    if not runtime.operational_lookups.is_overwatch_recipient(recipient):
        return
    outcomes = await reset_project_application_caches(runtime.operational_lookups)
    await wa.send_message(to=recipient, text=_format_cache_reset_outcomes(outcomes))
