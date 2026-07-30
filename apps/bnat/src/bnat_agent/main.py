"""Burger Nation FastAPI application assembly."""

from bnat_agent.identity import IDENTITY, PRESENTATION
from bnat_agent.rest_agent.agent_recipe import GRAPH_ADAPTER_FACTORY
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    CallbackButtonData,
    select_service_wa_send,
)
from restaurant_agent_runtime.web import AgentBindings, create_restaurant_app


def create_app(**factory_overrides):
    return create_restaurant_app(
        identity=IDENTITY,
        presentation=PRESENTATION,
        graph_adapter_factory=GRAPH_ADAPTER_FACTORY,
        agent_bindings=AgentBindings(
            callback_data_type=CallbackButtonData,
            select_service_sender=select_service_wa_send,
        ),
        **factory_overrides,
    )


app = create_app()
