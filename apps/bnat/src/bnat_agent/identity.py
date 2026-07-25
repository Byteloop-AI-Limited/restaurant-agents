"""Burger Nation-owned identity and presentation settings."""

from restaurant_agent_core import RestaurantIdentity, RestaurantPresentation

IDENTITY = RestaurantIdentity(rest_ref="BNAT", waba_namespace="bnat")
PRESENTATION = RestaurantPresentation(
    display_name="Burger Nation",
    logo_url=(
        "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/"
        "bnat/bnat_logo.jpg"
    ),
)
