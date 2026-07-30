"""SFCS FastAPI application assembly."""

from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    CallbackButtonData,
    select_service_wa_send,
)
from restaurant_agent_runtime.web import AgentBindings, create_restaurant_app
from sfcs_agent.identity import IDENTITY, PRESENTATION
from sfcs_agent.rest_agent.agent_recipe import GRAPH_ADAPTER_FACTORY

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
