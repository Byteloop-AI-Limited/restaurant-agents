"""
Ordelo backend REST API service for customer operations
  . Provides async methods to create/update customers via Ordelo API
  . Handles customer address updates with webhook notifications
  . Manages customer-restaurant consent mapping upserts
  . Loads Ordelo-owned operational configuration
  . Uses httpx async client with centralized base URL resolution
Functions/Classes:
  . OrdeloService
    . get_or_create_customer_master
    . create_or_update_customer
    . update_address
    . update_cust_rest_map
"""

# %%
from __future__ import annotations

from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)
from restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel import (
    CustomerMaster,
    CreateOrUpdateCustomerRequest,
    UpdateAddressRequest,
    UpdateCustRestMapRequest,
    RestaurantFeedbackRequest,
)
from restaurant_agent_runtime.services.ordelo_service.datamodels.cust_rest_map_pymodel import CustRestMap


class OrdeloService(BaseModel):
    """Service client for Ordelo backend REST API customer operations."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rest_ref: str
    database_client: Any
    operational_lookups: OperationalLookupCache

    async def _get_base_url(self) -> str:
        """Fetch Ordelo base URL through the runtime-owned TTL cache."""
        return self.operational_lookups.get_app_url("ORDELO")

    async def create_or_update_customer(
        self, request: CreateOrUpdateCustomerRequest
    ) -> Optional[dict]:
        """
        Create or update a customer in customer_master.

        Args:
            request: Customer data payload.

        Returns:
            Response JSON dict, or None on error.
        """
        base_url = await self._get_base_url()
        url = f"{base_url}/customer-hooks/create-or-update-customer"

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(url, json=request.model_dump(exclude_none=True))
                res.raise_for_status()
                return res.json()
            except httpx.HTTPError as e:
                logger.error(f"Error creating/updating customer {request.cust_id}: {e}")
                return None

    async def update_address(self, request: UpdateAddressRequest) -> Optional[dict]:
        """
        Update customer delivery address and notify restaurant.

        Args:
            request: Address update payload.

        Returns:
            Response JSON dict, or None on error.
        """
        base_url = await self._get_base_url()
        url = f"{base_url}/customer-hooks/update-address"

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(url, json=request.model_dump(exclude_none=True))
                res.raise_for_status()
                return res.json()
            except httpx.HTTPError as e:
                logger.error(
                    f"Error updating address for customer {request.cust_id}: {e}"
                )
                return None

    async def update_cust_rest_map(
        self, request: UpdateCustRestMapRequest
    ) -> Optional[dict]:
        """
        Upsert customer-restaurant consent mapping.

        Args:
            request: Consent mapping payload.

        Returns:
            Response JSON dict, or None on error.
        """
        base_url = await self._get_base_url()
        url = f"{base_url}/customer-hooks/update-cust-rest-map"

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    url, json=request.model_dump(mode="json", exclude_none=True)
                )
                res.raise_for_status()
                return res.json()
            except httpx.HTTPError as e:
                logger.error(
                    f"Error updating cust_rest_map for {request.cust_id}/{request.rest_ref}: {e}"
                )
                return None

    async def submit_restaurant_feedback(
        self, request: RestaurantFeedbackRequest
    ) -> Optional[dict]:
        """Ask Ordelo to schedule restaurant-admin feedback notifications."""
        base_url = await self._get_base_url()
        url = f"{base_url}/customer-hooks/restaurant-feedback"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url, json=request.model_dump(exclude_none=True), timeout=10.0
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                logger.error(
                    "Could not schedule restaurant feedback for {}: {}",
                    request.rest_ref,
                    exc,
                )
                return None

    async def get_or_create_customer_master(
        self, recipient: str, wa_name: Optional[str] = None
    ) -> tuple[CustomerMaster, bool]:
        """
        Fetch existing customer or create a new one via Ordelo API.

        Args:
            recipient: Customer phone number (cust_id).
            wa_name: WhatsApp display name, mapped to cust_name if provided.

        Returns:
            Tuple of (CustomerMaster, ask_for_consent).
        """
        try:
            customer = CustomerMaster.from_cust_id(
                recipient,
                database_client=self.database_client,
            )
            customer_exists = True
        except ValueError:
            customer_exists = False

        if not customer_exists:
            # If new customer, create customer record
            result = await self.create_or_update_customer(
                CreateOrUpdateCustomerRequest(
                    cust_id=recipient,
                    rest_ref=self.rest_ref,
                    cust_name=wa_name,
                )
            )
            customer = CustomerMaster(**result)
            ask_for_consent = True

        elif customer_exists and wa_name is not None:
            # Update customer name if provided
            result = await self.create_or_update_customer(
                CreateOrUpdateCustomerRequest(
                    cust_id=recipient,
                    rest_ref=self.rest_ref,
                    cust_name=wa_name,
                )
            )
            customer = CustomerMaster(**result)
            try:
                consent = CustRestMap.from_cust_id_and_rest_ref(
                    recipient,
                    self.rest_ref,
                    database_client=self.database_client,
                )
                ask_for_consent = consent.ask_for_marketing_consent(30)
            except ValueError:
                ask_for_consent = True
        else:
            try:
                consent = CustRestMap.from_cust_id_and_rest_ref(
                    recipient,
                    self.rest_ref,
                    database_client=self.database_client,
                )
                ask_for_consent = consent.ask_for_marketing_consent(30)
            except ValueError:
                ask_for_consent = True

        return customer, ask_for_consent


# %%
"""

# %%

svc = OrdeloService(rest_ref="ELAS")
await svc.get_or_create_customer_master("447448440754", wa_name="ha ha")

# %%

"""
