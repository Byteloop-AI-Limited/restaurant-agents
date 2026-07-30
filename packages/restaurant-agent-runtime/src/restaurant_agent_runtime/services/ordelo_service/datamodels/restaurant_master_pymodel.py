"""
Pydantic model for restaurant_master table
    . Defines fields and types to match the restaurant_master DDL
    . Handles nullability with Optional
    . Depends on pydantic, datetime, and config.client_ordelo
    . Models the restaurant_master table structure
    . Provides from_rest_ref to instantiate from DB
    . Provides get_admins to fetch admins column live from DB
    . Includes restaurant configuration: stale thread timeout, weekly service hours
    . Parses service_hours_json into a WeeklySchedule on row load
  Functions/Classes:
    . RestaurantMaster
        . from_rest_ref
        . get_admins
"""

# %%
import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from restaurant_agent_runtime.services.service_hours import WeeklySchedule
from restaurant_agent_runtime.services.tz_utils import UK_TZ


class RestaurantMaster(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    rest_ref: str  # character varying, NOT NULL
    rest_id: Optional[str] = None  # character varying, NULL
    rest_name: str  # text, NOT NULL
    rest_email: Optional[str] = None  # text, NULL
    admins: Optional[list[str]] = None  # text[], NULL
    house_number: str  # text, NOT NULL
    building_name: Optional[str] = None  # text, NULL
    street_name: str  # text, NOT NULL
    city: str  # text, NOT NULL
    postcode: str  # text, NOT NULL
    lat: float  # double precision, NOT NULL
    lon: float  # double precision, NOT NULL
    dt: datetime.date  # date, NOT NULL
    dtts: datetime.datetime  # timestamp with time zone, NOT NULL
    rest_stale_active_threads_minutes: int = 10  # integer, NOT NULL, DEFAULT 10
    service_hours_json: dict[str, Any] = Field(default_factory=dict)  # jsonb, NOT NULL
    service_hours: WeeklySchedule

    @model_validator(mode="before")
    @classmethod
    def _build_service_hours(cls, values: Any) -> Any:
        if isinstance(values, dict) and "service_hours" not in values:
            raw = values.get("service_hours_json") or {}
            values["service_hours"] = WeeklySchedule.from_dict(raw, tz=UK_TZ)
        return values

    @classmethod
    def from_rest_ref(cls, rest_ref: str):
        from restaurant_agent_runtime.config import client_ordelo

        resp = (
            client_ordelo.table("restaurant_master")
            .select("*")
            .eq("rest_ref", rest_ref.upper())
            .execute()
        )
        data = (
            resp["data"]
            if isinstance(resp, dict) and "data" in resp
            else resp.data
            if hasattr(resp, "data")
            else None
        )
        if not data or len(data) == 0:
            raise ValueError(f"No restaurant found with rest_ref={rest_ref}")
        # Use the first row
        row = data[0]
        return cls(**row)

    def get_admins(self):
        """
        Fetches the current value of the 'admins' column from the DB for this restaurant.
        Returns a list of admin strings, or None if not set.
        """
        from restaurant_agent_runtime.config import client_ordelo

        resp = (
            client_ordelo.table("restaurant_master")
            .select("admins")
            .eq("rest_ref", self.rest_ref)
            .execute()
        )
        data = (
            resp["data"]
            if isinstance(resp, dict) and "data" in resp
            else resp.data
            if hasattr(resp, "data")
            else None
        )
        if not data or len(data) == 0:
            raise ValueError(f"No restaurant found with rest_ref={self.rest_ref}")
        return data[0].get("admins")


# %%
# _rm = RestaurantMaster.from_rest_ref("SFCS")
# print(_rm.service_hours)
# from restaurant_agent_runtime.config import client_ordelo
# client_ordelo.table("restaurant_master").select("*").eq("rest_ref", "WREN").execute()
