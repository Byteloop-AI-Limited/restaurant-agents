"""Burger Nation-owned identity and presentation settings."""

from restaurant_agent_runtime import (
    DEFAULT_ENQUIRY_OPTIONS,
    EnquiryMenu,
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
    takeaway_button_label="Collection (10% off)",
    delivery_promo_caption="Limited Time Offer - 15% off on all delivery orders",
    takeaway_promo_caption="Limited Time Offer - 10% off on all takeaway orders",
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        options=DEFAULT_ENQUIRY_OPTIONS,
    ),
)
