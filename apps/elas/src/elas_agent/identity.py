"""ELAS-owned identity and presentation settings.

Unlike BNAT and SFCS, this app serves two restaurant brands (Elai and Wings
and Things) behind one WhatsApp number and one `RestaurantIdentity`. The
`restaurant_selection` config below is the only thing that varies per brand;
every other setting (hours, address, min-order/delivery-area, customer
master, consent, thread namespace) stays canonical `ELAS`, matching the
Ordelo-side `CHKS -> ELAS` alias.
"""

from restaurant_agent_runtime import (
    DEFAULT_ENQUIRY_OPTIONS,
    EnquiryMenu,
    EnquiryOption,
    RestaurantChoice,
    RestaurantIdentity,
    RestaurantPresentation,
    RestaurantSelection,
)

IDENTITY = RestaurantIdentity(rest_ref="ELAS", waba_namespace="elas")

RESTAURANT_SELECTION = RestaurantSelection(
    prompt="Which restaurant would you like to order from?",
    choices=(
        RestaurantChoice(
            rest_ref="ELAS",
            title="Elai",
            display_name="Elai",
            human_message="I want to order from Elai",
            logo_url=(
                "https://raw.githubusercontent.com/Byteloop-AI-Limited/"
                "elai-menu-images/main/images/elas_logo.jpg"
            ),
            supports_dine_in=True,
        ),
        RestaurantChoice(
            rest_ref="CHKS",
            title="Wings and Things",
            display_name="Wings and Things",
            human_message="I want to order from Wings and Things",
            # elai's live _send_menu_tool uses state["rest_ref"], which its
            # /SelectRestRef callback sets to "chks" — confirmed via
            # rest_agent/agent_wa_senders.py:select_rest_ref_wa_send and
            # agents/agent_harness.py:_send_menu_tool. A "wits" filename also
            # exists in the same image repo but is only referenced by a
            # commented-out, never-invoked carousel template experiment
            # (services/wa_templates/rest_menu_wa_template.py) — not the live
            # path. "chks" is the confirmed-correct slug for both the image
            # and the menu-link URL.
            logo_url=(
                "https://raw.githubusercontent.com/Byteloop-AI-Limited/"
                "elai-menu-images/main/images/chks_logo.jpg"
            ),
            supports_dine_in=False,
            # No per-brand promo override: Elai and Wings and Things share
            # the same delivery/takeaway promo, set once on PRESENTATION
            # below rather than duplicated on each RestaurantChoice.
        ),
    ),
)

PRESENTATION = RestaurantPresentation(
    display_name="Elai",
    contact_phone="01722656888",
    logo_url=(
        "https://raw.githubusercontent.com/Byteloop-AI-Limited/"
        "elai-menu-images/main/images/elas_logo.jpg"
    ),
    delivery_button_label="Delivery (10% off)",
    takeaway_button_label="Takeaway",
    delivery_promo_caption="Limited Time Offer - 10% off on all delivery orders",
    # takeaway_promo_caption left unset: no discount for takeaway, falls
    # back to the default plain caption.
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        button_title="Choose an option",
        options=(
            *DEFAULT_ENQUIRY_OPTIONS,
            # Shown for both brands (Elai and Wings and Things); Wings and
            # Things has supports_dine_in=False, so transfer_to_dinein's
            # existing guard (not a hidden row) declines politely — see
            # ADR-0023. No `description`: a "Elai only" subtitle would also
            # render for Elai customers, where it reads wrong.
            EnquiryOption("Book a table", "I want to book a table"),
        ),
    ),
    restaurant_selection=RESTAURANT_SELECTION,
    reservation_base_url="https://elai-reservation.byteloop.ai",
)
