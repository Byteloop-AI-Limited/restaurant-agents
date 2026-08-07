"""Runtime rendering for app-owned system prompts."""

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.prompts import PromptTemplate

from restaurant_agent_runtime.rest_agent.agents.agent_harness import ContextSchema


def render_prompt_middleware(prompt: str):
    """Build a dynamic system prompt with current restaurant authority values."""
    template = PromptTemplate.from_template(prompt)

    @dynamic_prompt
    def render(request: ModelRequest) -> str:
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
        return template.format(
            restaurant_name=context.restaurant_name,
            restaurant_address=address,
            restaurant_phone=context.restaurant_contact_phone or "not available",
            venue_hours=master.service_hours.format_week(),
            delivery_order_hours=master.service_hours.format_new_order_week(),
            takeaway_order_hours=master.service_hours.format_new_order_week(),
        )

    return render
