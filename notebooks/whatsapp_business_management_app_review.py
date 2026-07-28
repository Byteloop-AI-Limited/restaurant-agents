"""App Review demonstration for ``whatsapp_business_management``.

Open this file as a Jupyter-style Python notebook. Editors that support percent
cells will render ``# %%`` as code cells and ``# %% [markdown]`` as Markdown.
"""

# %% [markdown]
# # `whatsapp_business_management` App Review demonstration
#
# This recording demonstrates how the application uses Meta's WhatsApp Business
# Management API after a restaurant grants access to its WhatsApp Business
# Account (WABA).
#
# The application performs three relevant operations:
#
# 1. Read the business phone numbers belonging to the selected WABA.
# 2. Read the applications currently subscribed to the WABA's webhooks.
# 3. Subscribe this application to the WABA's webhooks after onboarding.
#
# This is a backend integration, so it does not have a separate WABA-management
# user interface. The notebook executes the same Graph API operations used by
# the service.
#
# **Recording safety**
#
# - Use a dedicated test WABA, or an account whose owner explicitly authorised
#   the demonstration.
# - Never display an access token, app secret, verification token, or PIN.
# - Crop or blur identifiers visible in Meta's interfaces.
# - The notebook masks identifiers before printing API responses.

# %% [markdown]
# ## Meta screen to show before running the notebook
#
# In another browser window, open:
#
# **Meta Business Settings → Accounts → WhatsApp accounts → select the test
# WABA → Open in WhatsApp Manager → Phone numbers**
#
# Meta occasionally changes the navigation labels. If they differ, open the
# WhatsApp Manager page titled **Phone numbers** for the test WABA.
#
# Briefly show that the WABA has a registered business phone number. Blur the
# business name, complete phone number, WABA ID, and phone-number ID. It is safe
# to leave only the last four characters visible so they can be compared with
# the masked notebook response.
#
# Suggested on-screen caption:
#
# > The restaurant has granted our application access to this WhatsApp Business
# > Account. Our service reads its registered business phone-number assets.

# %% Imports and secret-safe configuration
from __future__ import annotations

import json
import os
from getpass import getpass
from typing import Any

import requests


GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0").removeprefix("v")
ACCESS_TOKEN = os.getenv("META_APP_REVIEW_ACCESS_TOKEN") or getpass(
    "Meta access token (input hidden): "
)
WABA_ID = os.getenv("META_APP_REVIEW_WABA_ID") or getpass(
    "Test WABA ID (input hidden): "
)

if not ACCESS_TOKEN.strip():
    raise RuntimeError("A Meta access token is required.")
if not WABA_ID.strip():
    raise RuntimeError("A test WABA ID is required.")

GRAPH_BASE_URL = f"https://graph.facebook.com/v{GRAPH_API_VERSION}"
HTTP_TIMEOUT_SECONDS = 30

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {ACCESS_TOKEN}"})


def mask_value(value: Any, *, visible_suffix: int = 4) -> str:
    """Mask a value while retaining a short suffix for visual comparison."""
    text = str(value)
    if len(text) <= visible_suffix:
        return "****"
    return f"****{text[-visible_suffix:]}"


SENSITIVE_KEY_PARTS = (
    "id",
    "link",
    "name",
    "phone",
    "token",
    "url",
)


def _looks_secret(text: str) -> bool:
    """Detect URLs and token-bearing strings that must never be displayed."""
    lowered = text.lower()
    return (
        lowered.startswith(("http://", "https://"))
        or "access_token" in lowered
        or "token=" in lowered
    )


def sanitise_payload(value: Any, *, parent_key: str = "") -> Any:
    """Recursively mask identifiers and names before displaying a response."""
    if isinstance(value, dict):
        return {
            key: sanitise_payload(item, parent_key=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitise_payload(item, parent_key=parent_key) for item in value]
    if any(part in parent_key.lower() for part in SENSITIVE_KEY_PARTS):
        return mask_value(value)
    # Graph pagination links can embed the access token. Mask URL or
    # token-bearing strings even when their parent key looks harmless.
    if isinstance(value, str) and _looks_secret(value):
        return "****"
    return value


def masked_edge(edge: str) -> str:
    """Return an endpoint path that is safe to display in the recording."""
    return edge.replace(WABA_ID, mask_value(WABA_ID))


def graph_request(
    method: str,
    edge: str,
    *,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Call Meta Graph API and print only a sanitised response."""
    response = session.request(
        method=method,
        url=f"{GRAPH_BASE_URL}/{edge.lstrip('/')}",
        params=params,
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    print(f"{method.upper()} /{masked_edge(edge.lstrip('/'))}")
    print(f"HTTP status: {response.status_code}")

    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as error:
        raise RuntimeError("Meta returned a non-JSON response.") from error

    if not response.ok:
        # Do not print the raw error because it can contain account identifiers.
        error_type = payload.get("error", {}).get("type", "GraphAPIError")
        raise RuntimeError(
            f"Meta Graph API request failed with HTTP {response.status_code} "
            f"({error_type})."
        )

    print("Sanitised response:")
    print(json.dumps(sanitise_payload(payload), indent=2, sort_keys=True))
    return payload


print(f"Graph API version: v{GRAPH_API_VERSION}")
print(f"Test WABA: {mask_value(WABA_ID)}")
print("Access token loaded without displaying it.")

# %% [markdown]
# ## 1. Read the WABA's business phone numbers
#
# Keep the WhatsApp Manager **Phone numbers** page visible briefly, then run the
# next cell. The API response should correspond to the phone-number asset shown
# in WhatsApp Manager.
#
# This call demonstrates that the application can read phone-number assets from
# a WABA that the restaurant granted it access to.
#
# Suggested on-screen caption:
#
# > `GET /{WABA_ID}/phone_numbers` uses `whatsapp_business_management` to read
# > the restaurant's registered business phone numbers.

# %% Read business phone-number assets
phone_numbers_response = graph_request(
    "GET",
    f"{WABA_ID}/phone_numbers",
    params={"fields": "id,display_phone_number,verified_name"},
)

# %% [markdown]
# ## 2. Check the WABA's application subscriptions
#
# The next request checks whether this Meta application is subscribed to the
# selected WABA's webhook events.
#
# Suggested on-screen caption:
#
# > `GET /{WABA_ID}/subscribed_apps` reads the applications that receive webhook
# > events for this WABA.

# %% Read the current WABA webhook subscriptions
subscriptions_before = graph_request("GET", f"{WABA_ID}/subscribed_apps")

# %% [markdown]
# ## Meta screen to show before the subscription operation
#
# Open the application under review in:
#
# **Meta for Developers → My Apps → select the app → WhatsApp → Configuration**
#
# Briefly show the **Webhook** section and its configured callback URL. Blur the
# hostname if it identifies a private environment, and never reveal the verify
# token or app secret.
#
# This screen shows the webhook configuration owned by the app. The WABA-level
# association itself is verified by the `/subscribed_apps` API calls below.
#
# Suggested on-screen caption:
#
# > After onboarding, our backend subscribes the application to the restaurant's
# > WABA so Meta can deliver WhatsApp webhook events to this configured endpoint.

# %% [markdown]
# ## 3. Subscribe the application to the WABA's webhooks
#
# **This is the only write operation in the notebook.** Run it only against the
# dedicated test WABA, or with the WABA owner's explicit authorisation.
#
# The cell requires the exact confirmation phrase before sending the request.
# Anything else safely skips the write.

# %% Manage the WABA webhook subscription (guarded write)
confirmation = input(
    "Type SUBSCRIBE TEST WABA to perform the management API write, "
    "or press Enter to skip: "
)

subscription_write_response: dict[str, Any] | None = None
if confirmation == "SUBSCRIBE TEST WABA":
    subscription_write_response = graph_request(
        "POST",
        f"{WABA_ID}/subscribed_apps",
    )
else:
    print("Write skipped; no WABA subscription was changed.")

# %% [markdown]
# ## 4. Verify the resulting WABA subscription
#
# Run this read-only request after the subscription call. The sanitised response
# should show that an application is subscribed to the WABA.
#
# Suggested on-screen caption:
#
# > The follow-up request confirms the business-management operation succeeded.

# %% Verify the WABA webhook subscription
subscriptions_after = graph_request("GET", f"{WABA_ID}/subscribed_apps")

# %% [markdown]
# ## End of demonstration
#
# The recording has now shown the complete `whatsapp_business_management` use
# case:
#
# - A restaurant-owned WABA and its phone number were identified in WhatsApp
#   Manager.
# - The application read the WABA's registered business phone-number assets.
# - The application inspected the WABA's webhook subscriptions.
# - With explicit authorisation, the application subscribed itself to the WABA.
# - A follow-up request verified the resulting subscription.
#
# Stop the recording here. Do not open notebook variables, request headers,
# environment variables, browser developer tools, or configuration objects,
# because they may expose credentials or complete account identifiers.
