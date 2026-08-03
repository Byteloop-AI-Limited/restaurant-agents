# Operational Lookup Cache

Each `RestaurantRuntime` owns one process-local `OperationalLookupCache`. It
reduces repeated reads of stable operational configuration without creating a
shared cache or changing the authority of the database.

## Cached lookups

| Lookup | Source of truth | TTL | Failure behaviour |
| --- | --- | --- | --- |
| Application URL (`*_APP_URL`) | `ordelo_config` | 60 minutes | Raise to the live caller; do not cache the failure |
| `RestaurantMaster` | `restaurant_master` | 5 minutes | Raise to the live caller; do not cache the failure |
| Overwatch recipients | `ordelo_config.overwatch_list` | 5 minutes | Fail closed; recipient is not privileged |

Overwatch values are comma-separated WhatsApp identifiers. They are normalized
without a leading `+`; the database value is the only allowlist source.

The cache has a per-key cold-load lock, uses a monotonic clock, and never
caches missing values, errors, or stale data. Order, payment, delivery,
customer, consent, and Thread lookups remain live transactional reads.

## Calling code

Runtime-bound code receives the cache through `RestaurantRuntime` or the graph
`ContextSchema`:

```python
ordelo_url = runtime.operational_lookups.get_app_url("ORDELO")
master = runtime.operational_lookups.get_restaurant_master()
is_operator = runtime.operational_lookups.is_overwatch_recipient(recipient)
```

Do not introduce module-global caches or instantiate a second cache inside a
handler or service.

## Reset endpoint

`POST /internal/cache/reset` clears entries in the current process only. It is
deliberately unauthenticated by the owner's operational decision; network
exposure remains an infrastructure responsibility. It returns no cached values.

| Query | Meaning |
| --- | --- |
| `scope=all` (default) | Clear every URL, RestaurantMaster, and Overwatch entry held by this runtime |
| `scope=operational_config` | Clear all URL entries, or one URL entry selected by `app_ref` |
| `scope=restaurant_master` | Clear only the current runtime's RestaurantMaster entry |
| `scope=overwatch` | Clear only the current runtime's Overwatch allowlist entry |

`app_ref` is allowed only with `scope=operational_config`. Supported values are
`ORDELO`, `RESTAURANT_MENU`, and the running app's `rest_ref` (for example,
`SFCS` on an SFCS instance). Passing it with any other scope returns `422`; an
unsupported reference returns `404`.

### Calls

Use the deployed URL of the Restaurant Application whose process you intend to
clear. The default call clears every cached operational lookup:

```bash
curl --fail --request POST 'https://rest-agent.example/internal/cache/reset'
```

Use a narrow scope when only one source changed:

```bash
# RestaurantMaster/service hours/order-cutoff change
curl --fail --request POST \
  'https://rest-agent.example/internal/cache/reset?scope=restaurant_master'

# Ordelo Overwatch allowlist change
curl --fail --request POST \
  'https://rest-agent.example/internal/cache/reset?scope=overwatch'

# All application URLs in this Restaurant Application
curl --fail --request POST \
  'https://rest-agent.example/internal/cache/reset?scope=operational_config'

# Only the Ordelo URL entry; RESTAURANT_MENU and the running rest_ref are also valid
curl --fail --request POST \
  'https://rest-agent.example/internal/cache/reset?scope=operational_config&app_ref=ORDELO'
```

Every successful response contains the requested scope, the optional `app_ref`,
and removal counts; no cached values are returned:

```json
{
  "scope": "overwatch",
  "app_ref": null,
  "removed_entries": {
    "operational_config": 0,
    "restaurant_master": 0,
    "overwatch": 1
  }
}
```

In a multi-instance deployment, call the endpoint on every instance or wait for
the relevant TTL.
