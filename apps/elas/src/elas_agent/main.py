"""ELAS FastAPI application assembly."""

from elas_agent.identity import IDENTITY, PRESENTATION
from elas_agent.rest_agent.agent_recipe import GRAPH_ADAPTER_FACTORY
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
        include_reservation_router=True,
        **factory_overrides,
    )


app = create_app()
