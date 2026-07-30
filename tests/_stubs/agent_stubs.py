"""
Agent module stubs for isolated agent unit tests
    . Provides fake WhatsApp clients and thread handlers for runtime contexts
    . Provides lightweight agent harness and LangChain factory stubs
    . Avoids compiling real agents or touching external services during tests
  Functions/Classes:
    . FakeWaClient
    . FakeThreadHandler
    . build_runtime
    . build_agent_harness_stub
    . build_langchain_agents_stub
    . build_lg_utils_agent_stub
"""

from types import ModuleType, SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict


class FakeWaClient:
    def __init__(self):
        self.sent_messages = []
        self.sent_locations = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)

    async def send_location(self, **kwargs):
        self.sent_locations.append(kwargs)


class FakeThreadHandler:
    def __init__(self):
        self.inactive_recipients = []
        self.thread_id = "thread-1"
        self.is_new_thread = False

    async def make_threads_inactive(self, recipient):
        self.inactive_recipients.append(recipient)

    async def get_or_create_thread(self, recipient):
        return self.thread_id, self.is_new_thread


def build_runtime(**context_overrides):
    context = SimpleNamespace(
        recipient="447000000001",
        rest_ref="SFCS",
        wa_client=FakeWaClient(),
        thread_handler=FakeThreadHandler(),
        pool=object(),
        client_ordelo=None,
    )
    for key, value in context_overrides.items():
        setattr(context, key, value)
    return SimpleNamespace(context=context)


def _transfer_command(name):
    return Command(
        graph=Command.PARENT,
        goto=name,
        update={"active_agent": name},
    )


def build_agent_harness_stub():
    module = ModuleType(
        "restaurant_agent_runtime.rest_agent.agents.agent_harness"
    )

    class ContextSchema(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

    module.AgentState = dict
    module.ContextSchema = ContextSchema
    module.cleanup_before_model = lambda *args, **kwargs: None
    module.respond_on_wa = lambda *args, **kwargs: None
    def send_takeaway_menu_tool(*args, **kwargs):
        """Send the takeaway menu in tests."""
        return "takeaway menu sent"

    def send_restaurant_menu_tool(*args, **kwargs):
        """Send the restaurant menu in tests."""
        return "restaurant menu sent"

    def transfer_to_delivery(*args, **kwargs):
        """Transfer to delivery agent in tests."""
        return _transfer_command("delivery_agent")

    def transfer_to_takeaway(*args, **kwargs):
        """Transfer to takeaway agent in tests."""
        return _transfer_command("takeaway_agent")

    def transfer_to_triage(*args, **kwargs):
        """Transfer to triage agent in tests."""
        return _transfer_command("triage_agent")

    module.send_takeaway_menu_tool = send_takeaway_menu_tool
    module.send_restaurant_menu_tool = send_restaurant_menu_tool
    module.transfer_to_delivery = transfer_to_delivery
    module.transfer_to_takeaway = transfer_to_takeaway
    module.transfer_to_triage = transfer_to_triage
    return module


def build_langchain_agents_stub():
    module = ModuleType("langchain.agents")
    module.create_agent_calls = []

    class FakeAgent:
        def __init__(self):
            self.invoke_result = AIMessage("agent response")

        def invoke(self, state):
            return self.invoke_result

    def create_agent(**kwargs):
        module.create_agent_calls.append(kwargs)
        return FakeAgent()

    module.create_agent = create_agent
    return module


def build_lg_utils_agent_stub():
    module = ModuleType("restaurant_agent_runtime.services.lg_utils")
    module.llm_settings = SimpleNamespace(
        llm_client=object(),
        llm_client_single_tool_turn=object(),
    )
    module.create_agent_w_sys_prompt_n_tools_calls = []

    class FakeAgent:
        def __init__(self):
            self.invoke_result = AIMessage("agent response")

        def invoke(self, state):
            return self.invoke_result

    def create_agent_w_sys_prompt_n_tools(**kwargs):
        module.create_agent_w_sys_prompt_n_tools_calls.append(kwargs)
        return FakeAgent()

    module.create_agent_w_sys_prompt_n_tools = create_agent_w_sys_prompt_n_tools
    return module
