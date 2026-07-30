# Caching System

## Overview

The Elai application implements an in-memory caching system to reduce database queries and improve performance. The caching mechanism is centralized in `config/params.py` and provides TTL-based (Time To Live) caching for restaurant configuration data.

## Cache Types

### 1. Base URL Cache (`_BASE_URL_CACHE`)

**Purpose**: Caches restaurant base URLs fetched from the `ordelo_config` table.

**Storage**: `dict[str, tuple[str, float]]`
- Key: Restaurant reference (e.g., "ELAS", "WREN")
- Value: Tuple of (base_url, expiry_timestamp)

**TTL**: 5 minutes

**Usage**:
```python
from config.params import get_restaurant_base_url_async

base_url = await get_restaurant_base_url_async("ELAS")
# Returns: "https://api.restaurant.com"
```

### 2. RestaurantMaster Cache (`_RESTAURANT_MASTER_CACHE`)

**Purpose**: Caches `RestaurantMaster` instances to avoid repeated database queries.

**Storage**: `dict[str, tuple[RestaurantMaster, float]]`
- Key: Restaurant reference (e.g., "ELAS", "WREN")
- Value: Tuple of (RestaurantMaster instance, expiry_timestamp)

**TTL**: 5 minutes

**Usage**:
```python
from config.params import get_restaurant_master_cached

restaurant = get_restaurant_master_cached("ELAS")
# Returns: RestaurantMaster instance with all restaurant data
```

## Cache Mechanism

### How It Works

1. **Cache Lookup**: When data is requested, the system first checks if a valid cached entry exists
2. **Expiry Check**: If cached data exists, checks if `current_time < expiry_timestamp`
3. **Cache Hit**: Returns cached data if valid
4. **Cache Miss**: Fetches from database, stores with new expiry timestamp, and returns data
5. **Auto-Eviction**: Expired entries are removed on next access attempt

### Cache Key Normalization

All restaurant references are normalized to uppercase before caching:
```python
rest_ref_upper = rest_ref.upper()  # "elas" → "ELAS"
```

## API Functions

### Core Functions

#### `get_restaurant_base_url_async(rest_ref: str) -> str`
Fetches restaurant base URL with caching.

**Parameters**:
- `rest_ref`: Restaurant reference code (e.g., "ELAS", "WREN")

**Returns**: Base URL string

**Raises**: `ValueError` if no config found

**Example**:
```python
url = await get_restaurant_base_url_async("ELAS")
```

#### `get_restaurant_master_cached(rest_ref: str) -> RestaurantMaster`
Fetches RestaurantMaster instance with caching.

**Parameters**:
- `rest_ref`: Restaurant reference code

**Returns**: RestaurantMaster instance

**Raises**: `ValueError` if no restaurant found

**Example**:
```python
restaurant = get_restaurant_master_cached("ELAS")
admins = restaurant.get_admins()
```

### Cache Management Functions

#### `reset_restaurant_base_url_cache(rest_ref: str | None = None) -> int`
Clears base URL cache entries.

**Parameters**:
- `rest_ref`: Optional. If provided, clears only that restaurant's cache. If None, clears entire cache.

**Returns**: Number of entries removed

**Example**:
```python
# Clear specific restaurant
removed = reset_restaurant_base_url_cache("ELAS")  # Returns: 1

# Clear all
removed = reset_restaurant_base_url_cache()  # Returns: total count
```

#### `reset_restaurant_master_cache(rest_ref: str | None = None) -> int`
Clears RestaurantMaster cache entries.

**Parameters**:
- `rest_ref`: Optional. If provided, clears only that restaurant's cache. If None, clears entire cache.

**Returns**: Number of entries removed

**Example**:
```python
# Clear specific restaurant
removed = reset_restaurant_master_cache("ELAS")  # Returns: 1

# Clear all
removed = reset_restaurant_master_cache()  # Returns: total count
```

## REST API Endpoints

### Cache Reset Endpoints

#### `POST /restaurant-base-url-cache/reset`

Resets the in-memory restaurant base URL cache.

**Query Parameters**:
- `rest_ref` (optional): Restaurant reference code

**Response**:
```json
{
  "scope": "ELAS",  // or "ALL" if no rest_ref provided
  "removed_entries": 1
}
```

**Examples**:
```bash
# Clear specific restaurant cache
curl -X POST "http://localhost:3101/restaurant-base-url-cache/reset?rest_ref=ELAS"

# Clear entire cache
curl -X POST "http://localhost:3101/restaurant-base-url-cache/reset"
```

#### `POST /restaurant-master-cache/reset`

Resets the in-memory RestaurantMaster cache.

**Query Parameters**:
- `rest_ref` (optional): Restaurant reference code

**Response**:
```json
{
  "scope": "WREN",  // or "ALL" if no rest_ref provided
  "removed_entries": 1
}
```

**Examples**:
```bash
# Clear specific restaurant cache
curl -X POST "http://localhost:3101/restaurant-master-cache/reset?rest_ref=WREN"

# Clear entire cache
curl -X POST "http://localhost:3101/restaurant-master-cache/reset"
```

## Configuration

### Cache TTL

The cache TTL is configured in `config/params.py`:

```python
_CACHE_TTL_SECS = 5 * 60  # 5 minutes
```

To modify the TTL, update this constant. The change will apply to both cache types.

## Implementation Details

### Cache Storage Structure

```python
# Base URL Cache
_BASE_URL_CACHE: dict[str, tuple[str, float]] = {}
# Example entry: {"ELAS": ("https://api.elas.com", 1735200000.0)}

# RestaurantMaster Cache
_RESTAURANT_MASTER_CACHE: dict[str, tuple[RestaurantMaster, float]] = {}
# Example entry: {"ELAS": (RestaurantMaster(...), 1735200000.0)}
```

### Time Tracking

The system uses `time.monotonic()` for expiry tracking, which is immune to system clock adjustments:

```python
now = time.monotonic()
expires_at = now + _CACHE_TTL_SECS
_BASE_URL_CACHE[cache_key] = (base_url, expires_at)
```

### Cache Invalidation Strategy

**Lazy Eviction**: Expired entries are only removed when accessed, not proactively.

**Manual Invalidation**: Use reset functions or REST endpoints to force cache clearing.

## Use Cases

### When to Use Caching

1. **Frequent reads**: Data accessed multiple times within 5 minutes
2. **Expensive queries**: Database queries that are costly to repeat
3. **Stable data**: Restaurant configuration that changes infrequently

### When to Clear Cache

1. **Configuration updates**: After updating restaurant settings in the database
2. **Debugging**: When troubleshooting configuration issues
3. **Testing**: Before running tests that require fresh data
4. **Deployment**: After deploying changes to restaurant configuration

## Best Practices

1. **Always use cached functions**: Prefer `get_restaurant_master_cached()` over `RestaurantMaster.from_rest_ref()`
2. **Clear cache after updates**: Reset cache after modifying restaurant configuration in the database
3. **Monitor cache hits**: Check logs for cache hit/miss patterns (debug level)
4. **Adjust TTL if needed**: Increase TTL for more stable data, decrease for frequently changing data

## Logging

The caching system logs at DEBUG level:

```python
logger.debug(f"Using cached base URL for {rest_ref_upper}: {cached_value}")
logger.debug(f"Fetched base URL for {rest_ref_upper}: {base_url}")
logger.debug(f"Using cached RestaurantMaster for {rest_ref_upper}")
logger.debug(f"Fetched and cached RestaurantMaster for {rest_ref_upper}")
```

Cache reset operations log at INFO level:

```python
logger.info(f"Cleared entire base URL cache ({count} entries)")
logger.info(f"Cleared base URL cache for {cache_key}")
logger.info(f"No cache entry found for {cache_key}")
```

## Code References

**File**: `config/params.py`
- Lines 26-31: Cache storage definitions
- Lines 54-84: `get_restaurant_master_cached` implementation
- Lines 97-108: `get_restaurant_base_url_async` implementation
- Lines 183-214: Cache reset functions

**File**: `watomation/fapp.py`
- Lines 245-262: Base URL cache reset endpoint
- Lines 266-281: RestaurantMaster cache reset endpoint

## Future Enhancements

Potential improvements to consider:

1. **Redis integration**: Move to distributed cache for multi-instance deployments
2. **Cache warming**: Pre-populate cache on application startup
3. **Metrics**: Track cache hit/miss ratios
4. **Configurable TTL**: Per-restaurant or per-data-type TTL settings
5. **Cache size limits**: Implement LRU eviction for memory management
