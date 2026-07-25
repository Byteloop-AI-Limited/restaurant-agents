"""
Restaurant master data loading and dictionary filtering utilities
  . Loads RestaurantMaster data from project settings with caching
  . Provides filter_dict function for list of dictionaries filtering
  . Logs restaurant reference and admin information on initialization
  . Provides webhook URL construction helpers with caching (5 min TTL)
  . Exposes service hour configuration derived from REST_MASTER
  . Implements in-memory caching for base URLs and RestaurantMaster instances
  . Cache reset automatically reloads REST_MASTER and updates derived constants
  Functions/Classes:
    . REST_MASTER
    . get_restaurant_base_url_async
    . get_restaurant_webhook_url_async
    . reset_restaurant_base_url_cache
    . reset_restaurant_master_cache
    . get_restaurant_master_cached
    . get_restaurant_admins
    . filter_dict
"""

# %%
import time

from loguru import logger
from restaurant_agent_core.services.ordelo_service.datamodels.restaurant_master_pymodel import (
    RestaurantMaster,
)
from restaurant_agent_core.config import client_ordelo

_CACHE_TTL_SECS = 5 * 60  # 5 minutes
_BASE_URL_CACHE: dict[str, tuple[str, float]] = {}
_RESTAURANT_MASTER_CACHE: dict[str, tuple["RestaurantMaster", float]] = {}


# %% Webhook path mapping - type to path suffix (no base URLs)
WEBHOOK_PATHS = {
    "rider-inflight": "rider-event-hooks/rider-inflight",
    "rider-rest-cc": "rider-event-hooks/on-restaurant-cc",
    "rider-cust-cc": "rider-event-hooks/on-customer-cc",
    "rider-rest-enter": "rider-event-hooks/on-restaurant-enter",
    "rider-cust-enter": "rider-event-hooks/on-customer-enter",
    "delivery-timedout": "rider-event-hooks/delivery-timedout",
    "order-payment-complete": "order-event-hooks/payment-complete/",
    "order-address-update": "order-event-hooks/address-update",
}


# %% get_restaurant_master_cached
def get_restaurant_master_cached(
    rest_ref: str,
) -> RestaurantMaster:
    """
    Get RestaurantMaster instance with in-memory caching.

    Queries restaurant_master table and caches result for 5 minutes.

    Args:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN")

    Returns:
        RestaurantMaster instance

    Raises:
        ValueError: If no restaurant found for the given rest_ref
    """
    rest_ref_upper = rest_ref.upper()
    cache_key = rest_ref_upper
    now = time.monotonic()

    cached = _RESTAURANT_MASTER_CACHE.get(cache_key)
    if cached:
        cached_value, expires_at = cached
        if expires_at > now:
            return cached_value
        _RESTAURANT_MASTER_CACHE.pop(cache_key, None)

    restaurant = RestaurantMaster.from_rest_ref(rest_ref_upper)
    _RESTAURANT_MASTER_CACHE[cache_key] = (restaurant, now + _CACHE_TTL_SECS)
    return restaurant


# %% get_restaurant_base_url_async
async def get_restaurant_base_url_async(rest_ref: str) -> str:
    """
    Fetch restaurant base URL from database with in-memory caching.

    Queries ordelo_config table for {REST_REF}_APP_URL config key.
    Results are cached for 5 minutes to avoid repeated DB lookups.

    Args:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN")

    Returns:
        Base URL string (e.g., "https://api.restaurant.com")

    Raises:
        ValueError: If no config found for the given rest_ref
    """
    rest_ref_upper = rest_ref.upper()
    cache_key = rest_ref_upper
    now = time.monotonic()

    cached = _BASE_URL_CACHE.get(cache_key)
    if cached:
        cached_value, expires_at = cached
        if expires_at > now:
            logger.debug(f"Using cached base URL for {rest_ref_upper}: {cached_value}")
            return cached_value
        _BASE_URL_CACHE.pop(cache_key, None)

    config_key = rest_ref_upper + "_APP_URL"
    resp = (
        client_ordelo.table("ordelo_config")
        .select("config_value")
        .eq("config_key", config_key)
        .limit(1)
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
        raise ValueError(f"No config found for {config_key} in ordelo_config")

    base_url = data[0]["config_value"]
    _BASE_URL_CACHE[cache_key] = (base_url, now + _CACHE_TTL_SECS)
    logger.debug(f"Fetched base URL for {rest_ref_upper}: {base_url}")
    return base_url


# %% get_restaurant_webhook_url_async
async def get_restaurant_webhook_url_async(rest_ref: str, webhook_type: str) -> str:
    """
    Construct full webhook URL by fetching base URL from DB and appending path.

    This function performs a database lookup on every call (no caching).
    Use this for all outbound webhook calls to restaurant systems.

    Args:
        rest_ref: Restaurant reference code (e.g., "ELAS", "WREN", "ELAB")
        webhook_type: Type of webhook, must be one of:
            - "rider-inflight" - Rider assigned to delivery
            - "rider-rest-cc" - Restaurant confirmation code verified
            - "rider-cust-cc" - Customer confirmation code verified
            - "rider-rest-enter" - Rider entered restaurant zone
            - "rider-cust-enter" - Rider entered customer zone
            - "delivery-timedout" - Delivery timed out
            - "order-payment-complete" - Payment completed
            - "order-address-update" - Customer address updated

    Returns:
        Full webhook URL (e.g., "https://api.restaurant.com/rider-event-hooks/rider-inflight")

    Raises:
        ValueError: If webhook_type is not recognized or rest_ref config not found
    """
    path = WEBHOOK_PATHS.get(webhook_type.lower())
    if not path:
        valid_types = ", ".join(WEBHOOK_PATHS.keys())
        raise ValueError(
            f"Unknown webhook type: '{webhook_type}'. Valid types: {valid_types}"
        )

    base_url = await get_restaurant_base_url_async(rest_ref)
    full_url = f"{base_url}/{path}"
    logger.debug(f"Constructed webhook URL: {full_url}")
    return full_url


# %% reset_restaurant_base_url_cache
def reset_restaurant_base_url_cache(rest_ref: str | None = None) -> int:
    """
    Reset the in-memory restaurant base URL cache.

    Args:
        rest_ref: Optional restaurant reference code. If provided, clears only
                 that restaurant's cached base URL. If None, clears entire cache.

    Returns:
        Number of cache entries removed
    """
    if rest_ref is None:
        count = len(_BASE_URL_CACHE)
        _BASE_URL_CACHE.clear()
        logger.info(f"Cleared entire base URL cache ({count} entries)")
        return count
    else:
        cache_key = rest_ref.upper()
        if cache_key in _BASE_URL_CACHE:
            _BASE_URL_CACHE.pop(cache_key)
            logger.info(f"Cleared base URL cache for {cache_key}")
            return 1
        else:
            logger.info(f"No cache entry found for {cache_key}")
            return 0


# %% reset_restaurant_master_cache
def reset_restaurant_master_cache(rest_ref: str | None = None) -> int:
    """
    Reset the in-memory RestaurantMaster cache.

    Args:
        rest_ref: Optional restaurant reference code. If provided, clears only
                 that restaurant's cached instance. If None, clears entire cache.

    Returns:
        Number of cache entries removed
    """
    if rest_ref is None:
        count = len(_RESTAURANT_MASTER_CACHE)
        _RESTAURANT_MASTER_CACHE.clear()
        logger.info(f"Cleared entire RestaurantMaster cache ({count} entries)")
        return count
    else:
        cache_key = rest_ref.upper()
        if cache_key in _RESTAURANT_MASTER_CACHE:
            _RESTAURANT_MASTER_CACHE.pop(cache_key)
            logger.info(f"Cleared RestaurantMaster cache for {cache_key}")
            return 1
        else:
            logger.info(f"No cache entry found for {cache_key}")
            return 0


# %%
def get_restaurant_admins(
    rest_ref: str | None = None, rest_id: int | None = None
) -> list[str] | None:
    """Get restaurant admins by rest_ref or rest_id.

    Args:
        rest_ref: Restaurant reference code (e.g., "ELAS")
        rest_id: Restaurant ID

    Returns:
        List of admin identifiers, or None if no restaurant found
    """
    if rest_ref is None and rest_id is None:
        raise ValueError("Either rest_ref or rest_id must be provided")

    query = client_ordelo.table("restaurant_master").select("admins")

    if rest_ref is not None:
        query = query.eq("rest_ref", rest_ref.upper())
    else:
        query = query.eq("rest_id", rest_id)

    resp = query.execute()
    data = (
        resp["data"]
        if isinstance(resp, dict) and "data" in resp
        else resp.data
        if hasattr(resp, "data")
        else None
    )

    if not data or len(data) == 0:
        return None

    return data[0]["admins"]


# %%
# await get_restaurant_base_url_async("ELAS")
