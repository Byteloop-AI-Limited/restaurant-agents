"""
Pydantic models for takeaway operations
  . Defines TakeawaySummaryData model for takeaway order tracking
  . Defines RestaurantMasterData model for restaurant info in webhooks
  . Defines TakeawayPickupTimePayload for pickup time update webhook
  Functions/Classes:
    . TakeawaySummaryData
    . RestaurantMasterData
    . TakeawayPickupTimePayload
    . TakeawayReadyPayload
"""

# %%

from typing import Optional, List
from pydantic import BaseModel


class TakeawaySummaryData(BaseModel):
    """takeaway_summary fields from takeaway trigger payload."""

    order_number: str
    rest_id: str
    rest_name: str
    rest_address: str
    town: str
    customer_id: str
    customer_name: str
    restaurant_confirmation_status: str
    restaurant_update_dtts: Optional[str] = None
    restaurant_admin: Optional[str] = None
    status: str
    rest_confirmation_code: int
    rest_prep_time_minutes: Optional[int] = None
    rest_confirmation_method: Optional[str] = None
    restaurant_msg_id: Optional[str] = None
    customer_msg_id: Optional[str] = None
    pickup_time: Optional[str] = None
    pickup_date: str
    rest_ref: Optional[str] = None
    dt: str
    dtts: str


class RestaurantMasterData(BaseModel):
    """Restaurant master fields from restaurant_master table."""

    rest_id: str
    rest_ref: str
    rest_name: str
    admins: List[str]
    lon: float
    lat: float
    house_number: Optional[str] = None
    building_name: Optional[str] = None
    street_name: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None


class TakeawayPickupTimePayload(BaseModel):
    """Payload model for takeaway pickup time webhook."""

    takeaway_summary: TakeawaySummaryData
    restaurant_master: RestaurantMasterData


class TakeawayReadyPayload(BaseModel):
    """Payload model for takeaway-ready webhook."""

    order_id: str
    order_number: str
    recipient: str
    admin_id: str
    event: str
    event_dtts: str
