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

### Recipient-aware availability

`accepts_new_order(order_type, recipient, at=None)` and `is_open(recipient, at)`
are the single decision point for "can this recipient use the service right
now?". Both return `True` unconditionally for an Overwatch recipient and
otherwise delegate to the cached `RestaurantMaster`/`WeeklySchedule`. Every
service-button, transfer, menu-send, and out-of-hours gate calls one of these
two methods so an Overwatch recipient exercises the complete flow as if the
venue were inside its service interval — do not re-implement the
`is_overwatch_recipient(...) or ...accepts_new_order(...)` check inline at a
new call site.

For new-order interactions, the availability result is final: an approved
collection selection sends the menu directly, an approved delivery selection
continues to the address flow, and an unavailable normal recipient receives a
single `Ordering is currently closed.` message. The model must not ask for the
date or time or make a second hours decision.

```python
can_deliver = runtime.operational_lookups.accepts_new_order("delivery", recipient)
is_open_now = runtime.operational_lookups.is_open(recipient, datetime.now(UK_TZ))
```

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

## Overwatch project reset

WhatsApp `/reset-cache` is available only to an Overwatch recipient. It
force-refreshes `BNAT_APP_URL`, `SFCS_APP_URL`, and `ELAS_APP_URL` from
`ordelo_config`, then sends one `POST /internal/cache/reset?scope=all` request
to each configured URL. It reports each target's outcome and continues if one
target is unavailable or fails. It accepts no arguments.

The command makes one request per configured application URL, not one request
per deployed instance. Additional replicas must be reset separately or allowed
to expire their normal TTLs. `ORDELO_APP_URL` is refreshed for diagnostics but
is not a cache-reset target.

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
