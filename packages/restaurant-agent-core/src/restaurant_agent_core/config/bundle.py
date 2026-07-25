"""Build one restaurant's settings bundle from the shared AWS secret."""

from copy import copy

from restaurant_agent_core.runtime import RestaurantIdentity, RestaurantSettingsBundle
from restaurant_agent_core.utils.aws_setting import agent_env

from .google_setting import google_settings
from .llm_setting import llm_settings
from .microservices_setting import ms_settings
from .pg_setting import client_ordelo, pg_settings
from .project_setting import project_settings
from .stripe_setting import stripe_settings
from .waba_setting import WabaBusinessSettings


def load_settings_bundle(identity: RestaurantIdentity) -> RestaurantSettingsBundle:
    """Load strict namespaced WABA settings and shared service configuration."""

    project = copy(project_settings)
    project.rest_ref = identity.rest_ref
    return RestaurantSettingsBundle(
        project=project,
        database=pg_settings,
        database_client=client_ordelo,
        llm=llm_settings,
        payment=stripe_settings,
        maps=google_settings,
        microservices=ms_settings,
        waba=WabaBusinessSettings.for_namespace(identity.waba_namespace, agent_env),
    )
