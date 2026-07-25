"""Interactively inspect and update Burger Nation's Meta callback URL."""

# %% Load the BNAT WABA settings and construct a synchronous client.
from restaurant_agent_core.config.waba_setting import WabaBusinessSettings
from restaurant_agent_core.utils.aws_setting import agent_env
# agent_env.keys()
# %%

WABA_NAMESPACE = "lai"
CALLBACK_URL = "https://rest-agent-test.ordelo.app/"

waba_business_settings = WabaBusinessSettings.for_namespace(
    WABA_NAMESPACE,
    agent_env,
)
wa_client = waba_business_settings.create_sync_client()

# %% Inspect the callback configuration before updating it.
business_phone_number = wa_client.get_business_phone_number()
(
    business_phone_number.verified_name,
    business_phone_number.webhook_configuration,
)

# %% Update Meta. Executing this cell changes BNAT's live callback configuration.
# NOTE: This is not working - stopping here
update_result = wa_client.override_waba_callback_url(
    callback_url=CALLBACK_URL,
    verify_token=waba_business_settings.waa_verify_token,
    waba_id=waba_business_settings.waa_account_id,
)
update_result

# %% Fetch the configuration again to verify the update applied.
business_phone_number = wa_client.get_business_phone_number()
(
    business_phone_number.verified_name,
    business_phone_number.webhook_configuration,
)
