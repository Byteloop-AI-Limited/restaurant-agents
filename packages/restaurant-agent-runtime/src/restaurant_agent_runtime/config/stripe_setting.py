"""Payment service settings model for one restaurant runtime."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# %%
class StripeSetting(BaseSettings):
    url: str = Field(..., alias="ms_stripe_url")
    token: str = Field(..., alias="ms_stripe_token")
    reservation_url: str = Field(..., alias="ms_stripe_reservation_url")

    model_config = SettingsConfigDict(extra="allow")

    @property
    def headers(self):
        return {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {self.token}",
        }

    def generate_payment_intent_url(self, thread_id: str, order_id: str) -> str:
        """
        Generates the payment intent URL based on thread_id and order_id.

        Args:
            thread_id: The ID of the WA thread
            order_id: orderId

        Returns:
            The constructed payment intent URL
        """
        return f"{self.url}/threads/{thread_id}/orders/{order_id}/payment-url"
