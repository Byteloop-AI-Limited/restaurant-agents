"""Burger Nation-owned identity and presentation settings."""

from restaurant_agent_runtime import (
    EnquiryMenu,
    EnquiryOption,
    RestaurantIdentity,
    RestaurantPresentation,
)

IDENTITY = RestaurantIdentity(rest_ref="BNAT", waba_namespace="bnat")
PRESENTATION = RestaurantPresentation(
    display_name="Burger Nation Orpington",
    contact_phone="01689637476",
    logo_url=None,
    delivery_button_label="Delivery (15% off)",
    takeaway_button_label="Takeaway (10% off)",
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            EnquiryOption("Customer complaint", "I want to make a customer complaint"),
            EnquiryOption(
                "Parking availability", "I want to know about parking availability"
            ),
            EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
        ),
    ),
)
