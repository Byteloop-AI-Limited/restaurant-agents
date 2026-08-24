"""Operational URL diagnostics and bounded cross-application cache reset."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from restaurant_agent_runtime.services.operational_lookup_cache import (
    CACHE_RESET_APP_REFS,
    DIAGNOSTIC_APP_URL_REFS,
    OperationalLookupCache,
)

ResetOutcome = Literal["reset", "unavailable", "invalid_url", "failed"]


def application_url_details(
    operational_lookups: OperationalLookupCache,
    *,
    refresh: bool = False,
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Return sanitized app URLs and per-key availability errors.

    Normal diagnostics show the effective process-local cached values. The
    reset command uses ``refresh=True`` to replace them from ``ordelo_config``
    before it contacts another Restaurant Application.
    """

    values: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    get_url = (
        operational_lookups.refresh_app_url
        if refresh
        else operational_lookups.get_app_url
    )
    for app_ref in DIAGNOSTIC_APP_URL_REFS:
        key = f"{app_ref}_APP_URL"
        try:
            values[key] = get_url(app_ref)
        except Exception:
            values[key] = None
            errors[key] = "unavailable"
    return values, errors


async def reset_project_application_caches(
    operational_lookups: OperationalLookupCache,
) -> dict[str, ResetOutcome]:
    """Fresh-read and reset BNAT, SFCS, ELAS, and Ordelo cache processes once each."""

    fresh_urls, _ = await asyncio.to_thread(
        application_url_details,
        operational_lookups,
        refresh=True,
    )

    targets: dict[str, str] = {}
    outcomes: dict[str, ResetOutcome] = {}
    for app_ref in sorted(CACHE_RESET_APP_REFS):
        app_url = fresh_urls[f"{app_ref}_APP_URL"]
        if app_url is None:
            outcomes[app_ref] = "unavailable"
            continue
        try:
            targets[app_ref] = _cache_reset_url(app_url)
        except ValueError:
            outcomes[app_ref] = "invalid_url"

    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
        completed = await asyncio.gather(
            *(
                _reset_one_application_cache(client, app_ref, reset_url)
                for app_ref, reset_url in targets.items()
            )
        )
    outcomes.update(dict(completed))

    # If the request for this process reached itself, scope=all cleared its
    # just-refreshed entries. Read them again so subsequent diagnostics show
    # the current database values either way.
    await asyncio.to_thread(application_url_details, operational_lookups)
    return {app_ref: outcomes[app_ref] for app_ref in sorted(CACHE_RESET_APP_REFS)}


def _cache_reset_url(app_url: str) -> str:
    parsed = urlsplit(app_url.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Application URL must be an absolute HTTP(S) base URL")
    base = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", "")
    )
    return f"{base}/internal/cache/reset"


async def _reset_one_application_cache(
    client: httpx.AsyncClient,
    app_ref: str,
    reset_url: str,
) -> tuple[str, ResetOutcome]:
    try:
        response = await client.post(reset_url, params={"scope": "all"})
    except httpx.HTTPError:
        return app_ref, "failed"

    if not 200 <= response.status_code < 300:
        return app_ref, "failed"
    try:
        payload = response.json()
    except ValueError:
        return app_ref, "failed"
    if (
        not isinstance(payload, Mapping)
        or payload.get("scope") != "all"
        or not isinstance(payload.get("removed_entries"), Mapping)
    ):
        return app_ref, "failed"
    return app_ref, "reset"
