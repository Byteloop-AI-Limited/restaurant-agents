"""Inspect and update one restaurant app's WABA-level Meta callback URL."""

# %% Select the app, using the same names accepted by scripts/run-agent.sh.
from importlib import import_module

from restaurant_agent_runtime.config.waba_setting import WabaBusinessSettings
from restaurant_agent_runtime.utils.aws_setting import agent_env

APP = "sfcs"
CALLBACK_URL = "https://rest-agent-test.ordelo.app/"

identity_modules = {
    "bnat": "bnat_agent.identity",
    "sfcs": "sfcs_agent.identity",
}
try:
    identity_module = identity_modules[APP]
except KeyError as exc:
    supported_apps = ", ".join(identity_modules)
    raise ValueError(f"APP must be one of: {supported_apps}") from exc

IDENTITY = import_module(identity_module).IDENTITY

# %% Load the selected app's WABA settings and construct a synchronous client.
waba_business_settings = WabaBusinessSettings.for_namespace(
    IDENTITY.waba_namespace,
    agent_env,
)
wa_client = waba_business_settings.create_sync_client()
wa_client
# %% Inspect the phone's effective callback configuration before updating it.
business_phone_number = wa_client.get_business_phone_number(
    phone_id=waba_business_settings.waa_phone_id
)
(
    business_phone_number.verified_name,
    business_phone_number.webhook_configuration,
)


# %% Update the WABA-level callback. Executing this cell changes live Meta state.
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
