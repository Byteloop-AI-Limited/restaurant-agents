"""Inspect and update one restaurant app's WABA-level Meta callback URL."""

# %% Select the app, using the same names accepted by scripts/run-agent.sh.
from importlib import import_module

from restaurant_agent_runtime.config.bundle import load_settings_bundle

# APP = "bnat"
APP = "elas"
# APP = "sfcs"

# %%

identity_modules = {
    "bnat": "bnat_agent.identity",
    "sfcs": "sfcs_agent.identity",
    "elas": "elas_agent.identity",
}
try:
    identity_module = identity_modules[APP]
except KeyError as exc:
    supported_apps = ", ".join(identity_modules)
    raise ValueError(f"APP must be one of: {supported_apps}") from exc

IDENTITY = import_module(identity_module).IDENTITY

# %% Load the selected app's complete settings bundle and construct a synchronous client.
# This reads the shared AWS secret once, then selects only IDENTITY.waba_namespace.
settings = load_settings_bundle(IDENTITY)
waba_business_settings = settings.waba
wa_client = waba_business_settings.create_sync_client()
wa_client, waba_business_settings
# %% Inspect the phone's effective callback configuration before updating it.
business_phone_number = wa_client.get_business_phone_number(
    phone_id=waba_business_settings.waa_phone_id
)
(
    business_phone_number.verified_name,
    business_phone_number.webhook_configuration,
    waba_business_settings,
)


# %% Run - Update the WABA-level callback. Executing this cell changes live Meta state.
CALLBACK_URL = "https://rest-agent-test.ordelo.app/"
# CALLBACK_URL = "https://bnat-agent.fly.dev/"
# CALLBACK_URL = "https://sfcs-agent.fly.dev/"
# CALLBACK_URL = "https://elas-agg.ordelo.app/"

update_result = wa_client.override_waba_callback_url(
    callback_url=CALLBACK_URL,
    verify_token=waba_business_settings.waa_verify_token,
    waba_id=waba_business_settings.waa_account_id,
)
update_result

# %% Fetch the effective phone configuration again after the update.
business_phone_number = wa_client.get_business_phone_number(
    phone_id=waba_business_settings.waa_phone_id
)
(
    business_phone_number.verified_name,
    business_phone_number.webhook_configuration,
)
