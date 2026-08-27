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
        "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/bnat/bnat_menu_image.png"
    ),
    delivery_button_label="Delivery (10% Off)",
    takeaway_button_label="Collection",
    enquiry_button_label="More Options",
    delivery_promo_caption=(
        "📣 📣 Limited-time offer: 10% off delivery orders, or 15% with a valid coupon code. 🎁🎁"
    ),
    takeaway_promo_caption=(
        "📣 📣 Limited-time offer: 5% off collection orders over £25. 🎁🎁"
    ),
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        options=DEFAULT_ENQUIRY_OPTIONS,
    ),
)
