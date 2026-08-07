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
    logo_url=(
        "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/"
        "bnat/bnat_restaurant_menu_url.png"
    ),
    delivery_button_label="Delivery (15% off)",
    takeaway_button_label="Takeaway (10% off)",
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            EnquiryOption("Share feedback", "I want to share feedback"),
            EnquiryOption(
                "Parking availability", "I want to know about parking availability"
            ),
            EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
        ),
    ),
)
