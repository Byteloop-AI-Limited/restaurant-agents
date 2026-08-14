"""
Typed contracts for the customer-facing WaLocation client integration.
  . Request/response/callback models matching Ordelo's open POST /wa-request-location
  . Ordelo resolves rider identity and coordinates; the LLM never supplies them
Functions/Classes:
  . WaLocationRequest
  . WaLocationRequestOutcome
  . WaLocationPoint
  . WaLocationCallbackPayload
  . build_wa_location_callback_url
"""

# %%
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LocationRequester = Literal["customer", "restaurant_admin"]
LocationSource = Literal["whatsapp_current", "restaurant_confirmation"]


# %%
class WaLocationRequest(BaseModel):
    """One authorised caller requesting a location for one delivery order."""

    rest_ref: str = Field(min_length=1, max_length=20)
    order_number: str = Field(min_length=1, max_length=100)
    location_requested_by: LocationRequester
    requester_id: str = Field(min_length=1, max_length=50)
    callback_url: str = Field(min_length=1, max_length=2048)
    idempotency_key: Optional[str] = Field(default=None, max_length=255)


# %%
class WaLocationRequestOutcome(BaseModel):
    """Typed outcome of the outbound HTTP call, including failure detail.

    Unlike other ``OrdeloService`` methods, this is not a wire model and does
    not collapse every non-2xx response to ``None``: the delivery tool must
    distinguish ``409 food_not_picked_up`` from ``409 delivery_not_inflight``
    from a transport failure, each of which maps to different customer copy.
    """

    status_code: int
    status: Optional[str] = None
    code: Optional[str] = None
    request_id: Optional[str] = None


# %%
class WaLocationPoint(BaseModel):
    """One location observation as delivered in Ordelo's callback."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: LocationSource
    observed_at: str


# %%
class WaLocationCallbackPayload(BaseModel):
    """Open Ordelo-to-service location notification.

    ``extra="ignore"`` rather than ``forbid``: an Ordelo-side field addition
    must not 422 the callback and drop a pin that would otherwise send.
    """

    model_config = ConfigDict(extra="ignore")

    request_id: str
    order_number: str
    customer_id: str
    rider_id: str
    location_requested_by: LocationRequester
    requester_id: str
    location: WaLocationPoint


# %%
def build_wa_location_callback_url(base_url: str, rest_ref: str) -> str:
    """Build this app's callback URL for one restaurant's rider-event router.

    ``rstrip`` matters: seeded ``ordelo_config`` app URLs can end in a
    trailing slash, and an unstripped base produces a double slash that
    FastAPI redirects. Ordelo does not follow redirects, so an unstripped
    base silently fails every request with ``502 callback_delivery_failed``.
    """
    return f"{base_url.rstrip('/')}/rider-event-hooks/{rest_ref}/wa-location-response"
