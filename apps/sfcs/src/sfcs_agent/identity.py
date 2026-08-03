"""SFCS-owned identity and presentation settings."""

from restaurant_agent_runtime import (
    EnquiryMenu,
    EnquiryOption,
    RestaurantIdentity,
    RestaurantPresentation,
)

IDENTITY = RestaurantIdentity(rest_ref="SFCS", waba_namespace="sfcs")
PRESENTATION = RestaurantPresentation(
    display_name="Southern Fried Chicken - Salisbury",
    contact_phone="01722433714",
    delivery_button_label="Delivery (20% off)",
    takeaway_button_label="Collection (15% off)",
    enquiry_menu=EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            EnquiryOption("Customer complaint", "I want to make a customer complaint"),
            EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
        ),
    ),
    logo_url=(
        "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/"
        "sfcs/SFC+Logo+-+Red+Horizontal.png"
    ),
)
