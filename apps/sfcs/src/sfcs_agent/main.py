"""SFCS FastAPI application assembly."""

from restaurant_agent_core.web import AgentBindings, create_restaurant_app
from sfcs_agent.identity import IDENTITY, PRESENTATION
from sfcs_agent.rest_agent.agent_runner import SfcsGraphAdapter
from sfcs_agent.rest_agent.agent_wa_senders import (
    CallbackButtonData,
    select_service_wa_send,
)

def create_app(**factory_overrides):
    return create_restaurant_app(
        identity=IDENTITY,
        presentation=PRESENTATION,
        graph_adapter_factory=SfcsGraphAdapter,
        agent_bindings=AgentBindings(
            callback_data_type=CallbackButtonData,
            select_service_sender=select_service_wa_send,
        ),
        **factory_overrides,
    )


app = create_app()
