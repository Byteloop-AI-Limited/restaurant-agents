"""Runtime rendering for app-owned system prompts."""

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import SystemMessage
from langchain_core.prompts import PromptTemplate

from restaurant_agent_runtime.rest_agent.agents.agent_harness import ContextSchema
from restaurant_agent_runtime.rest_agent.restaurant_selection import selected_choice
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import SpecialistFlowView


def _retention_system_instruction(state: dict) -> str:
    """Compatibility adapter for callers of the former prompt-local helper."""
    return SpecialistFlowView.from_state(state).system_instruction()


def render_prompt_middleware(prompt: str):
    """Build a dynamic system prompt with current restaurant authority values."""
    template = PromptTemplate.from_template(prompt)

    @dynamic_prompt
    def render(request: ModelRequest) -> SystemMessage:
        context: ContextSchema = request.runtime.context
        master = context.restaurant_master
        address = ", ".join(
            part
            for part in (
                master.house_number,
                master.building_name,
                master.street_name,
                master.city,
                master.postcode,
            )
            if part
        )
        choice = selected_choice(request.state, context.restaurant_selection)
        if choice is not None:
            selected_restaurant_name = choice.display_name
        elif context.restaurant_selection is not None:
            selected_restaurant_name = "not yet selected"
        else:
            selected_restaurant_name = context.restaurant_name
        return SystemMessage(
            content=(
                template.format(
                    restaurant_name=context.restaurant_name,
                    restaurant_address=address,
                    restaurant_phone=context.restaurant_contact_phone
                    or "not available",
                    venue_hours=master.service_hours.format_week(),
                    delivery_order_hours=master.service_hours.format_new_order_week(),
                    takeaway_order_hours=master.service_hours.format_new_order_week(),
                    selected_restaurant_name=selected_restaurant_name,
                )
                + _retention_system_instruction(request.state)
            )
        )

    return render
