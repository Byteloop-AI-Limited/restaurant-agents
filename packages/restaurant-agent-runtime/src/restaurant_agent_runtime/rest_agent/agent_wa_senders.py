"""WhatsApp senders used by the standard Restaurant Agent graph."""

from typing import Literal

from pydantic import BaseModel
from pywa.types import Button, ButtonUrl, Section, SectionList, SectionRow
from pywa_async import WhatsApp

from restaurant_agent_runtime.runtime import EnquiryMenu, EnquiryOption, RestaurantSelection
from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)

class CallbackButtonData(BaseModel):
    model_config = {"frozen": True, "extra": "allow"}
    action: str
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
    *,
    operational_lookups: OperationalLookupCache,
    delivery_button_label: str = "Delivery",
    takeaway_button_label: str = "Takeaway",
    enquiry_button_label: str = "More options",
) -> None:
    """
    Sends order type selection buttons with rest_ref included.

    Args:
        recipient: Customer phone number
        wa_client: WhatsApp client instance
        rest_ref: Configured restaurant ID slug
        operational_lookups: Required availability source; determines which
            service buttons this recipient can see right now (Overwatch
            recipients always see every button).
    """
    normalized_rest_ref = str(rest_ref).lower()
    selection_text = "How can I help you today?"

    takeaway = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="takeaway_agent",
        human_msg="I want takeaway",
    )
    delivery = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="delivery_agent",
        human_msg="I want delivery",
    )
    inquiry = CallbackButtonData(
        action="/SelectService",
        rest_ref=normalized_rest_ref,
        active_agent="triage_agent",
        human_msg="I have an enquiry",
    )
    buttons = []
    if operational_lookups.accepts_new_order("delivery", recipient):
        buttons.append(Button(title=delivery_button_label, callback_data=delivery.model_dump_json()))
    if operational_lookups.accepts_new_order("takeaway", recipient):
        buttons.append(Button(title=takeaway_button_label, callback_data=takeaway.model_dump_json()))
    buttons.append(Button(title=enquiry_button_label, callback_data=inquiry.model_dump_json()))
    await wa_client.send_message(
        to=recipient,
        text=selection_text,
        buttons=buttons,
    )


# %% Restaurant selection (multi-restaurant apps only)
async def select_restaurant_wa_send(
    recipient: str,
    wa_client: WhatsApp,
    selection: RestaurantSelection,
) -> None:
    """Send the app-owned restaurant choices (WhatsApp permits at most three)."""
    buttons = [
        Button(
            title=choice.title,
            callback_data=CallbackButtonData(
                action="/SelectRestaurant",
                rest_ref=choice.rest_ref,
                human_msg=choice.human_message,
            ).model_dump_json(),
        )
        for choice in selection.choices
    ]
    await wa_client.send_message(
        to=recipient,
        text=selection.prompt,
        buttons=buttons,
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


def build_enquiry_callback_data(rest_ref: str, option: EnquiryOption) -> str:
    """Return the /SelectEnquiry payload for one option, byte-identical across senders.

    `active_agent` stays `"triage_agent"` for every option — including a
    dine-in booking option — so `human_message` reaches triage as a plain
    HumanMessage and the model routes it through the existing guarded
    `transfer_to_dinein` tool rather than bypassing its guards. See
    ADR-0023.
    """
    return CallbackButtonData(
        action="/SelectEnquiry",
        rest_ref=str(rest_ref).lower(),
        active_agent="triage_agent",
        human_msg=option.human_message,
    ).model_dump_json()


async def select_enquiry_wa_send(
    recipient: str,
    wa_client: WhatsApp,
    rest_ref: str,
    *,
    menu: EnquiryMenu,
    selected_rest_ref: str | None = None,
) -> None:
    """Send the app-owned enquiry choices as a WhatsApp SectionList (up to ten rows).

    `rest_ref` is the invariant app identity used in the callback payload.
    `selected_rest_ref` is the customer's chosen brand (for a multi-restaurant
    app) and only affects which rows are visible — see
    `EnquiryMenu.visible_options_for`. A single-restaurant app never passes
    it, so every option (none of which sets `only_for_rest_refs`) renders.
    """
    rows = [
        SectionRow(
            title=option.title,
            callback_data=build_enquiry_callback_data(rest_ref, option),
            description=option.description,
        )
        for option in menu.visible_options_for(selected_rest_ref)
    ]
    await wa_client.send_message(
        to=recipient,
        text=menu.prompt,
        buttons=SectionList(
            button_title=menu.button_title,
            sections=[Section(title=menu.button_title, rows=rows)],
        ),
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
# %% Handle sending restaurant menu carousel
from restaurant_agent_runtime.services.wa_templates.rest_menu_wa_template import (
    send_restaurant_menu_non_carousel,
)
from restaurant_agent_runtime.services.wa_templates.rest_menu_query_params import RestMenuQueryParams


# %%


async def send_restaurant_menu(
    recipient: str,
    thread_id: str,
    minimum_order: float,
    rest_ref: str,
    wa_client: WhatsApp,
    logo_url: str,
    operational_lookups,
    delivery_promo_caption: str,
    takeaway_promo_caption: str,
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
            operational_lookups=operational_lookups,
            delivery_promo_caption=delivery_promo_caption,
            takeaway_promo_caption=takeaway_promo_caption,
        )
    except ValueError as err:
        return err
    return None


# await send_restaurant_menu(recipient="447448440754", minimum_order=12, thread_id="12345")


# %% Dine-in reservation link (optional standard dine-in node only)
async def reservation_link_wa_send(
    recipient: str,
    reservation_url: str,
    wa_client: WhatsApp,
    wa_name: str = "there",
) -> None:
    await wa_client.send_message(
        to=recipient,
        header="Table Reservation",
        text=(
            f"Hi {wa_name}! \n\nPlease fill this form for reservation request. "
            "Once submitted we will be in touch with you to confirm. \n\n"
            "Thank you and goodbye."
        ),
        reply_to_message_id=None,
        buttons=ButtonUrl(title="Make Reservation", url=reservation_url),
    )


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
