"""
WhatsApp message handlers for customer interactions
    . Processes various types of incoming WhatsApp messages
    . Manages conversation flows using LangGraph for stateful dialogues
    . Simulates payment completion notifications via WhatsApp
    . Processes location data shared by customers
    . Provides testing utilities for WhatsApp features
    . Implements thread state management for conversation history
    . Bypasses the after-hours guard for whitelisted ALLOWED_USERS
    . Defers service-hour decisions to REST_MASTER.service_hours (WeeklySchedule)
  Functions/Classes:
    . simulate_payment_complete - Simulates order payment completion
    . handle_wa_msg_in_graph - Routes messages to appropriate graph handler
    . handle_wa_msg_status - Logs message delivery status
    . handle_adhoc_test - Test function for development purposes (delivery)
    . handle_adhoc_test_takeaway - Test function for takeaway flow
    . handle_request_location_response - Processes location data from customers
    . reset_thread - Resets conversation thread for clean state
    . is_outside_service_hours - Checks if message arrived outside restaurant hours
    . send_closed_message - Sends a message when the restaurant is closed
    . send_redirect_to_offline_mode - Sends a placeholder message for offline mode
    . _message_time_uk - Converts message timestamp to UK timezone
"""

# %%
from datetime import datetime, timezone

import httpx
from pywa.filters import from_users
from pywa.types import Message, MessageStatus
from pywa_async import WhatsApp, filters

from restaurant_agent_runtime.config import client_ordelo, logger, pg_settings
from restaurant_agent_runtime.config.params import get_restaurant_master_cached, get_restaurant_base_url_async
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.maps_service import address_resolver
from restaurant_agent_runtime.services.thread_management import ThreadHandler
from restaurant_agent_runtime.services.tz_utils import UK_TZ
from restaurant_agent_runtime.watomation.dedup import wa_dedup

# %% Allowed users list
ALLOWED_USERS = ["447448440754", "447446933210"]
ALLOWED_USERS_FILTER = from_users(",".join(ALLOWED_USERS))


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
    if msg.sender in ALLOWED_USERS:
        return False

    msg_time = _message_time_uk(msg)
    if msg_time is None:
        return False

    schedule = get_restaurant_master_cached(runtime.identity.rest_ref).service_hours
    return not schedule.is_open(msg_time)


def create_out_of_hours_filter(runtime: RestaurantRuntime):
    """Bind the filter to one restaurant instead of shared process state."""

    return filters.new(lambda wa, msg: is_outside_service_hours(wa, msg, runtime))


async def send_closed_message(
    wa: WhatsApp, msg: Message, *, runtime: RestaurantRuntime
):
    schedule = get_restaurant_master_cached(runtime.identity.rest_ref).service_hours
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


# %%

# WHEN_REST_MENU_REQUEST = filters.contains("/menu", ignore_case=True)


# async def handle_request_for_menu(wa: WhatsApp, msg: Message):
#     recipient = msg.sender
#     logger.info(f"check for id in msg: {msg.id}")
#     thread_id = msg.id
#     await send_restaurant_menu(
#         recipient=recipient, thread_id=thread_id, minimum_order=15
#     )

# %%

WHEN_PAYMENT_COMPLETE = filters.contains("/paid3100", ignore_case=True)


async def simulate_payment_complete(wa: WhatsApp, msg: Message):
    """
    Simulates a payment completion event for testing purposes.
        . Retrieves the latest order for the user that requires payment
        . Constructs a mock Stripe-like webhook payload
        . Sends a POST request to the local payment-hooks endpoint
        . Notifies the user if no eligible order is found
    """
    recipient = msg.sender
    ordelo_app_url = await get_restaurant_base_url_async("ORDELO")

    res = (
        client_ordelo.table("food_order")
        .select("order_id, payment_status")
        .eq("recipient", recipient)
        .order("order_dtts", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data or res.data[0].get("payment_status") != "requires_payment":
        await wa.send_message(
            to=recipient,
            text="No order requiring payment found.",
        )
        return

    # There is an order found and called the payment complete endpoint; Below mocks the stripe webhook call on successful payment.
    order_id = res.data[0]["order_id"]
    url = f"{ordelo_app_url}/payment-hooks/payment-complete"
    payload = {"data": {"object": {"metadata": {"orderID": order_id}}}}

    # follow_redirects=False on purpose: a redirect here (e.g. from a trailing-slash
    # mismatch normalised by an upstream proxy) would silently downgrade this POST to a
    # GET and surface as a confusing 405. Surface it loudly instead of following it.
    async with httpx.AsyncClient(follow_redirects=False) as client:
        try:
            response = await client.post(url, json=payload)
            if response.is_redirect:
                logger.error(
                    f"Unexpected redirect POSTing payment complete for {order_id}: "
                    f"{response.status_code} {url} -> {response.headers.get('location')}"
                )
                return
            response.raise_for_status()
            logger.info(f"Payment simulation success for {order_id}: {response.json()}")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error simulating payment for {order_id} at {e.request.url}: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Error simulating payment for {order_id}: {e}")


# %% Handle text in graph
@wa_dedup
async def handle_wa_msg_in_graph(
    wa: WhatsApp, msg: Message, *, graph_adapter: GraphAdapter
):
    await msg.indicate_typing()
    human_msg = msg.text
    wa_name: str = msg.from_user.name

    await graph_adapter.run_rest_graph_with_custom_msg(
        human_msg=human_msg, recipient=msg.sender, wa_name=wa_name
    )


# %%
async def handle_wa_msg_status(wa: WhatsApp, msg: MessageStatus):
    logger.info(f"Message status: {msg}")


# %%

WHEN_ADHOC_TEST = filters.contains("/test", ignore_case=True)


@wa_dedup
async def handle_adhoc_test(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
    graph_adapter: GraphAdapter,
):
    recipient = msg.sender
    # logger.critical("adhoc test")

    # Reset thread
    pool = await pg_settings.get_pool()
    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    await thread_handler.make_threads_inactive(recipient=recipient)
    await wa.send_message(to=recipient, text="Starting new conversation")

    # Cleanup the restaurant-local diagnostic delivery order.
    # order_id = "WWVP-26"
    order_id = "OOLX-24"
    order_number = f"{runtime.identity.rest_ref}-{order_id}"
    client_ordelo.rpc(
        "test_reset_order_and_dispatch",
        {"p_order_number": order_number},
    ).execute()

    state_update_dict = {
        "active_agent": "delivery_agent",
        "min_order_value": 8.9,
        "is_delivery": True,
        "order_id": order_id,
        "order_number": order_number,
        "is_payment_successful": True,
        "retain_thread": True,
    }

    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        human_msg="Payment is complete",
        state_update_dict=state_update_dict,
    )


# %% Handle testing of takeaway

WHEN_ADHOC_TEST_TAKEAWAY = filters.contains("/test-t", ignore_case=True)


@wa_dedup
async def handle_adhoc_test_takeaway(
    wa: WhatsApp,
    msg: Message,
    *,
    runtime: RestaurantRuntime,
    graph_adapter: GraphAdapter,
):
    recipient = msg.sender

    # Reset thread
    pool = await pg_settings.get_pool()
    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    await thread_handler.make_threads_inactive(recipient=recipient)
    await wa.send_message(to=recipient, text="Starting new conversation")

    # Cleanup takeaway
    order_id = "AZML-22"
    order_number = f"{runtime.identity.rest_ref}-{order_id}"
    client_ordelo.rpc(
        "test_reset_takeaway_order",
        {"p_order_number": order_number},
    ).execute()

    state_update_dict = {
        "active_agent": "takeaway_agent",
        "order_id": order_id,
        "order_number": order_number,
        "is_payment_successful": True,
        "retain_thread": True,
    }

    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        human_msg="Payment is complete",
        state_update_dict=state_update_dict,
    )


# %% Handle location
async def handle_request_location_response(wa: WhatsApp, msg: Message):
    location = msg.location
    address = address_resolver.get_address_from_coordinates(
        location.latitude, location.longitude
    )
    logger.info(f"Address: {address}")


# %% On reset
WHEN_RESET = filters.contains("/reset", ignore_case=True)


@wa_dedup
async def reset_thread(
    wa: WhatsApp, msg: Message, *, runtime: RestaurantRuntime
):
    logger.info("=============== reset the thread ===============")
    recipient = msg.from_user.wa_id

    pool = await pg_settings.get_pool()
    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    await thread_handler.make_threads_inactive(recipient=recipient)
    await wa.send_message(to=recipient, text="Starting new conversation")


# %% Debug state
WHEN_DEBUG = filters.contains("/debug", ignore_case=True)


def _format_debug_state(state: dict) -> str:
    lines = ["*Debug State*"]
    for key, value in state.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


async def handle_debug_state(
    wa: WhatsApp, msg: Message, *, graph_adapter: GraphAdapter
):
    recipient = msg.sender
    if recipient not in ALLOWED_USERS:
        return
    try:
        state = await graph_adapter.debug_state(recipient)
        text = _format_debug_state(state)
    except Exception as e:
        logger.error(f"Error fetching debug state for {recipient}: {e}")
        text = f"Error fetching debug state: {e}"
    await wa.send_message(to=recipient, text=text)
