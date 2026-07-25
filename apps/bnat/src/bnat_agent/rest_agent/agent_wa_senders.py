"""
WhatsApp messaging utilities for order management and address confirmation flows
    . Implements WhatsApp communication for delivery and order management
    . Defines reusable models for button callbacks with immutable properties
    . Supports extra fields in callback data (extra="allow") for flexibility
    . Sends admin notifications for order and delivery status updates
    . Provides interactive address confirmation flows with buttons
    . Implements postcode search/update flows via WhatsApp Flow API
    . Uses FlowButton for complex user interactions and form submissions
    . Fetches Ordelo app URL on demand via project_settings.getAudiloUrl for live location links
  Functions/Classes:
    . CallbackButtonData - Pydantic model for WhatsApp button callback data
    . admin_delivery_complete_notification - Notifies admins about completed deliveries
    . admin_order_reciept - Sends order receipts to admins with delivery details
    . confirm_delivery_address_wa - Sends address confirmation requests to customers
    . send_postcode_search_flow - Initiates postcode search flow via WhatsApp
    . reservation_link_wa_send - Sends reservation booking link button to customer
"""

# %%
from pywa.types import FlowButton, ButtonUrl
from pywa.types.flows import FlowActionType
from pydantic import BaseModel
from pywa.types import Button
import uuid
from pywa_async import WhatsApp
from typing import Literal
import pytz

uk_tz = pytz.timezone("Europe/London")


# %% reusable button callback model
class CallbackButtonData(BaseModel):
    model_config = {"frozen": True, "extra": "allow"}
    action: str


# %% Delivery or take away
async def delivery_or_takeaway(recipient: str, wa_client: WhatsApp):
    # for admin in temp_admins:
    delivery = CallbackButtonData(
        action="/DeliveryOrTakeaway-D",
        human_msg="I want Delivery",
    )
    takeaway = CallbackButtonData(
        action="/DeliveryOrTakeaway-T",
        human_msg="I want Takeaway",
    )

    await wa_client.send_message(
        to=recipient,
        header="Delivery Or Takeaway",
        text="I am happy to help you with your order, please select preferred option:\n",
        reply_to_message_id=None,
        buttons=[
            Button(title="Delivery", callback_data=delivery.model_dump_json()),
            Button(title="Takeaway", callback_data=takeaway.model_dump_json()),
        ],
    )
    return


# %%
async def send_welcome_msg_wa(
    recipient: str,
    user_name: str,
    wa_client: WhatsApp,
    restaurant_name: str,
) -> None:
    """
    Sends personalized welcome message.

    Args:
        recipient: Customer phone number
        user_name: Customer's WhatsApp name
        wa_client: WhatsApp client instance
    """
    body_text = f"""Hi {user_name}!\n
Welcome to *{restaurant_name}*. I am an AI Assistant to help you with your order."""

    await wa_client.send_message(to=recipient, text=body_text)


# %% Order type selection


async def select_service_wa_send(
    recipient: str,
    wa_client: WhatsApp,
    rest_ref: str,
) -> None:
    """
    Sends order type selection buttons with rest_ref included.

    Args:
        recipient: Customer phone number
        wa_client: WhatsApp client instance
        rest_ref: Configured restaurant ID slug
    """
    normalized_rest_ref = str(rest_ref).lower()
    selection_text = "How can I help you today?"

    takeaway = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="takeaway_agent",
        human_msg="I want Takeaway",
    )
    delivery = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="delivery_agent",
        human_msg="I want Delivery",
    )
    inquiry = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="triage_agent",
        human_msg="Inquiry",
    )

    await wa_client.send_message(
        to=recipient,
        text=selection_text,
        buttons=[
            Button(title="Delivery (20% off)", callback_data=delivery.model_dump_json()),
            Button(title="Collection (15% off)", callback_data=takeaway.model_dump_json()),
            Button(title="Inquiry", callback_data=inquiry.model_dump_json()),
        ],
    )


# %% Marketing consent selection
async def select_marketing_consent_wa_send(
    recipient: str,
    wa_client: WhatsApp,
    rest_ref: str | None,
) -> None:
    """
    Sends marketing consent buttons for the selected restaurant.

    Args:
        recipient: Customer phone number
        wa_client: WhatsApp client instance
        rest_ref: Selected restaurant slug, when known
    """
    consent_yes = CallbackButtonData(
        action="/SelectConsent",
        rest_ref=rest_ref,
        human_msg="Yes, send me marketing updates",
        response="yes",
    )
    consent_no = CallbackButtonData(
        action="/SelectConsent",
        rest_ref=rest_ref,
        human_msg="No, thanks",
        response="no",
    )

    await wa_client.send_message(
        to=recipient,
        text="Would you like to receive marketing updates from your selected restaurant?",
        buttons=[
            Button(title="Yes", callback_data=consent_yes.model_dump_json()),
            Button(title="No", callback_data=consent_no.model_dump_json()),
        ],
    )


# %%
async def confirm_delivery_address_wa(
    recipient: str, address: dict, wa_client: WhatsApp, header: str = None
):
    house_number = address.get("house_number", "")
    street = address.get("street_name", "")
    building = address.get("building", "")
    city = address.get("city", "")
    postcode = address.get("postcode", "")

    address_str = f"""
    {house_number} {building}
{street}
{city}
{postcode}
    """.strip()

    if not header:
        header = "Confirm or Update Delivery Address"

    address_confirmation_y = CallbackButtonData(
        action="/ConfirmDeliveryAddress",
        recipient=recipient,
        ai_msg=header,
        human_msg="Yes, this is my address",
        response="Yes",
    )
    address_confirmation_n = CallbackButtonData(
        action="/ConfirmDeliveryAddress",
        recipient=recipient,
        ai_msg=header,
        human_msg="No, I want to update my delivery address",
        response="No",
    )

    await wa_client.send_message(
        to=recipient,
        header=header,
        text=f"""
        {address_str}
        """,
        # footer='⚡ Powered by Ordelo',
        buttons=[
            Button(title="Yes", callback_data=address_confirmation_y.model_dump_json()),
            Button(
                title="Update", callback_data=address_confirmation_n.model_dump_json()
            ),
        ],
    )
    return


# %%
async def send_postcode_search_flow(
    recipient: str,
    wa_client: WhatsApp,
    customer_name: str = None,
    postcode_init: str = None,
):
    await wa_client.send_message(
        to=recipient,
        text="Please update your delivery address by filling the form below.",
        buttons=FlowButton(
            title="Update Address",
            flow_name="PostcodeSearch",
            flow_token=uuid.uuid4().hex,
            # mode=FlowStatus.DRAFT,
            flow_action_type=FlowActionType.NAVIGATE,
            flow_action_screen="START",  # The screen id to open when the user clicks the button
            flow_action_payload={
                "flow_name": "PostcodeSearch",
                "customer_id": recipient,
                "postcode_init": postcode_init,
            },
        ),
    )


# %% Handle sending restaurant menu carousel
from restaurant_agent_core.services.wa_templates.rest_menu_wa_template import (
    send_restaurant_menu_non_carousel,
)
from restaurant_agent_core.services.wa_templates.rest_menu_query_params import RestMenuQueryParams


# %%


async def send_restaurant_menu(
    recipient: str,
    thread_id: str,
    minimum_order: float,
    rest_ref: str,
    wa_client: WhatsApp,
    logo_url: str,
    order_type: Literal["delivery", "takeaway"] = "delivery",
    distance: float = 0.5,
) -> ValueError | None:
    rest_menu_query_params = RestMenuQueryParams(
        rest_ref=rest_ref,
        minimum_order=minimum_order,
        order_type=order_type,
        thread_id=thread_id,
        recipient=recipient,
    )
    # send_restaurant_menu_carousel(
    #     recipient=recipient,
    #     rest_menu_params=[rest_menu_query_params, rest_menu_query_params],
    # )
    try:
        await send_restaurant_menu_non_carousel(
            recipient=recipient,
            rest_menu=rest_menu_query_params,
            wa_client=wa_client,
            logo_url=logo_url,
        )
    except ValueError as err:
        return err
    return None


# await send_restaurant_menu(recipient="447448440754", minimum_order=12, thread_id="12345")


# %%
async def send_update_address_wa(
    recipient: str,
    wa_client: WhatsApp,
    rest_ref: str,
):
    rest_ref = rest_ref.lower()
    await wa_client.send_message(
        to=recipient,
        header="Update Address",
        text="Please update your delivery address by filling the form below.",
        reply_to_message_id=None,
        buttons=ButtonUrl(
            title="Update Address",
            # url=f"https://restaurant-test.ordelo.app/address-update?recipient={recipient}&rest_ref={rest_ref}",
            url=f"https://restaurant.ordelo.app/address-update?recipient={recipient}&rest_ref={rest_ref}",
        ),
    )


# %% Send reservation link
async def reservation_link_wa_send(
    recipient: str,
    reservation_url: str,
    wa: WhatsApp,
    wa_name: str = "There",
):
    await wa.send_message(
        to=recipient,
        header="Table Reservation",
        text=f"Hi {wa_name}! \n\nPlease fill this form for reservation request. Once submitted we will be in touch with you to confirm. \n\nThank you and goodbye.",
        reply_to_message_id=None,
        buttons=ButtonUrl(title="Make Reservation", url=reservation_url),
    )


# %%
"""
# %%
await send_postcode_search_flow(recipient="447448440754", postcode_init="BR6 6DN")
# %%
"""
# %%
