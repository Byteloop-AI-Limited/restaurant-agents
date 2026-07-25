"""SFCS-owned identity and presentation settings."""

from restaurant_agent_core import RestaurantIdentity, RestaurantPresentation

IDENTITY = RestaurantIdentity(rest_ref="SFCS", waba_namespace="sfcs")
PRESENTATION = RestaurantPresentation(
    display_name="Southern Fried Chicken - Salisbury",
    contact_phone="01722433714",
    logo_url=(
        "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/"
        "sfcs/SFC+Logo+-+Red+Horizontal.png"
    ),
)
