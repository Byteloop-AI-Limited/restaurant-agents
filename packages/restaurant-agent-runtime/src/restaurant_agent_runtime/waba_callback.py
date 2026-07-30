"""Fail-before-write checks for WABA callback administration."""

import asyncio
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from restaurant_agent_runtime.config.waba_setting import WABA_VALIDATE_UPDATES
from restaurant_agent_runtime.runtime import RestaurantIdentity, RestaurantRuntime


class CallbackValidationError(RuntimeError):
    """Raised when callback identities or effective configuration do not agree."""


def mask_secret(value: str, *, visible_suffix: int = 4) -> str:
    """Return a comparison hint without exposing the credential."""

    if visible_suffix < 1:
        raise ValueError("visible_suffix must be positive")
    if len(value) <= visible_suffix:
        return "****"
    return f"****{value[-visible_suffix:]}"


def runtime_waba_details(identity: RestaurantIdentity, settings: Any) -> dict[str, Any]:
    """Build the non-secret WABA identity exposed by the running application."""

    return {
        "rest_ref": identity.rest_ref,
        "waba_namespace": identity.waba_namespace,
        "waba_id": str(settings.waa_account_id),
        "phone_id": str(settings.waa_phone_id),
        "app_id": str(settings.waa_app_id),
        "token_hint": mask_secret(settings.waa_token),
        "app_secret_hint": mask_secret(settings.waa_app_secret),
        "validate_updates": WABA_VALIDATE_UPDATES,
    }


def resolve_effective_callback_url(
    webhook_configuration: Mapping[str, Any] | None,
) -> str | None:
    """Resolve Meta's effective callback using its override precedence."""

    configuration = webhook_configuration or {}
    for scope in ("phone_number", "whatsapp_business_account", "application"):
        callback_url = configuration.get(scope)
        if isinstance(callback_url, str) and callback_url.strip():
            return callback_url
    return None


def _restaurant_master_details(rest_ref: str) -> dict[str, Any]:
    """Load cached restaurant diagnostics without importing config at startup."""

    from restaurant_agent_runtime.config.params import get_restaurant_master_cached

    restaurant = get_restaurant_master_cached(rest_ref)
    return {
        "admins": restaurant.admins,
        "service_hours": restaurant.service_hours_json,
    }


async def _meta_runtime_details(runtime: RestaurantRuntime) -> dict[str, Any]:
    phone = await runtime.async_wa_client.get_business_phone_number(
        phone_id=runtime.settings.waba.waa_phone_id
    )
    return {
        "display_number": phone.display_phone_number,
        "callback_url": resolve_effective_callback_url(phone.webhook_configuration),
    }


async def build_runtime_details(runtime: RestaurantRuntime) -> dict[str, Any]:
    """Enrich local runtime identity without making diagnostics unavailable."""

    details = runtime_waba_details(runtime.identity, runtime.settings.waba)
    details.update(
        {
            "display_number": None,
            "admins": None,
            "service_hours": None,
            "callback_url": None,
            "configured_callback_url": runtime.settings.waba.waa_callback_url,
            "details_errors": {},
        }
    )

    async def load_meta_details():
        try:
            return await _meta_runtime_details(runtime), None
        except Exception:
            return {}, "unavailable"

    async def load_restaurant_details():
        try:
            return await asyncio.to_thread(
                _restaurant_master_details, runtime.identity.rest_ref
            ), None
        except Exception:
            return {}, "unavailable"

    (
        (meta_details, meta_error),
        (restaurant_details, restaurant_error),
    ) = await asyncio.gather(load_meta_details(), load_restaurant_details())
    details.update(meta_details)
    details.update(restaurant_details)
    if meta_error:
        details["details_errors"]["meta"] = meta_error
    if restaurant_error:
        details["details_errors"]["restaurant_master"] = restaurant_error
    return details


def normalize_callback_url(callback_url: str) -> str:
    """Normalize equivalent callback URLs for exact comparisons."""

    parsed = urlsplit(callback_url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise CallbackValidationError("Callback URL must be an absolute HTTP(S) URL")
    if parsed.fragment:
        raise CallbackValidationError("Callback URL must not contain a fragment")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, "")
    )


def validate_runtime_details(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> None:
    """Require the tunnel to expose the exact selected runtime identity."""

    if not isinstance(actual, Mapping):
        raise CallbackValidationError("Callback runtime details must be an object")
    mismatches = sorted(
        field
        for field, expected_value in expected.items()
        if actual.get(field) != expected_value
    )
    if mismatches:
        raise CallbackValidationError(
            "Callback runtime identity mismatch for: " + ", ".join(mismatches)
        )


def validate_token_app_binding(
    wa_client: Any,
    settings: Any,
    *,
    request_get: Callable[..., Any] = httpx.get,
    timeout: float = 15.0,
) -> None:
    """Require the WABA token to have been issued by the configured Meta app."""

    try:
        app_access_token = wa_client.get_app_access_token(
            app_id=int(settings.waa_app_id),
            app_secret=settings.waa_app_secret,
        )
    except Exception:
        raise CallbackValidationError(
            "Configured app ID and app secret could not obtain an app access token"
        ) from None

    try:
        response = request_get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": settings.waa_token},
            headers={"Authorization": f"Bearer {app_access_token}"},
            timeout=timeout,
        )
        response.raise_for_status()
        token_data = response.json()["data"]
        if not isinstance(token_data, Mapping):
            raise TypeError
    except Exception:
        raise CallbackValidationError(
            "Unable to inspect the configured WABA token"
        ) from None

    if token_data.get("is_valid") is not True:
        raise CallbackValidationError("Configured WABA token is not valid")
    if str(token_data.get("app_id")) != str(settings.waa_app_id):
        raise CallbackValidationError(
            "Configured WABA token was issued by a different Meta app"
        )


def validate_waba_phone_binding(wa_client: Any, settings: Any) -> None:
    """Require the configured phone to be owned by the configured WABA."""

    try:
        phone_ids = {
            str(phone.id)
            for phone in wa_client.get_business_phone_numbers(
                waba_id=settings.waa_account_id
            )
        }
    except Exception:
        raise CallbackValidationError(
            "Unable to inspect phone numbers for the configured WABA"
        ) from None

    if str(settings.waa_phone_id) not in phone_ids:
        raise CallbackValidationError(
            "Configured phone ID does not belong to the configured WABA"
        )


def override_waba_callback_url(wa_client: Any, settings: Any, callback_url: str) -> Any:
    """Perform the one intentional live write after all preflight checks pass."""

    return wa_client.override_waba_callback_url(
        callback_url=callback_url,
        verify_token=settings.waa_verify_token,
        waba_id=settings.waa_account_id,
    )


def validate_callback_update(
    *,
    settings: Any,
    callback_url: str,
    subscriptions: Mapping[str, Any],
    webhook_configuration: Mapping[str, Any] | None,
) -> None:
    """Verify the WABA override and reject a conflicting phone-level override."""

    target = normalize_callback_url(callback_url)
    matching_app = next(
        (
            item
            for item in subscriptions.get("data", ())
            if str(item.get("whatsapp_business_api_data", {}).get("id"))
            == str(settings.waa_app_id)
        ),
        None,
    )
    if matching_app is None:
        raise CallbackValidationError(
            "Configured Meta app is not subscribed to the configured WABA"
        )

    configured_override = matching_app.get("override_callback_uri")
    if not configured_override or normalize_callback_url(configured_override) != target:
        raise CallbackValidationError(
            "Configured WABA callback override does not match the target URL"
        )

    effective = webhook_configuration or {}
    waba_override = effective.get("whatsapp_business_account")
    if waba_override and normalize_callback_url(waba_override) != target:
        raise CallbackValidationError(
            "Effective WABA callback does not match the target URL"
        )

    phone_override = effective.get("phone_number")
    if phone_override and normalize_callback_url(phone_override) != target:
        raise CallbackValidationError(
            "A higher-precedence phone callback override conflicts with the target URL"
        )
