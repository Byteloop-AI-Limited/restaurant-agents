"""Build one RestaurantSettingsBundle at the application composition root."""

from restaurant_agent_runtime.runtime import RestaurantIdentity, RestaurantSettingsBundle
from restaurant_agent_runtime.utils.aws_setting import (
    DEFAULT_AGENT_SECRET_NAME,
    get_agent_env,
)

from .google_setting import GoogleSettings
from .llm_setting import LLMSettings
from .ordelo_setting import OrdeloSetting
from .pg_setting import PgSetting
from .project_setting import ProjectSetting
from .stripe_setting import StripeSetting
from .waba_setting import WabaBusinessSettings


def load_settings_bundle(identity: RestaurantIdentity) -> RestaurantSettingsBundle:
    """Load AWS once, validate settings, and build one isolated app bundle."""

    env_values = get_agent_env(secret_name=DEFAULT_AGENT_SECRET_NAME)
    if not env_values:
        raise RuntimeError(
            "Unable to load application settings from AWS Secrets Manager. "
            "Check AWS_SETTINGS_* configuration and IAM permissions."
        )

    project = ProjectSetting(**env_values).model_copy(
        update={"rest_ref": identity.rest_ref}
    )
    database = PgSetting(**env_values)
    return RestaurantSettingsBundle(
        project=project,
        database=database,
        database_client=database.client,
        llm=LLMSettings(**env_values),
        payment=StripeSetting(**env_values),
        maps=GoogleSettings(**env_values),
        waba=WabaBusinessSettings.for_namespace(identity.waba_namespace, env_values),
        ordelo=OrdeloSetting(**env_values),
    )
