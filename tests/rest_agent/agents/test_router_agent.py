"""
Unit tests for the agent router
    . Stubs services.lg_utils.LLM_CLIENT before importing router_agent
    . Asserts that run_router_agent forwards the human message and returns the LLM's next_agent
  Functions/Classes:
    . FakeStructuredOutput
    . FakeLLM
    . test_run_router_agent_returns_query_agent
    . test_run_router_agent_returns_takeaway_agent
    . test_run_router_agent_returns_dinein_agent
    . test_run_router_agent_passes_human_message
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda


class FakeLLM:
    def __init__(self, response="queryAgent"):
        self.response = response
        self.last_schema = None

    def with_structured_output(self, schema):
        self.last_schema = schema
        response = self.response
        return RunnableLambda(lambda payload: {"next_agent": response})


@pytest.fixture
def router_module(monkeypatch):
    fake_llm = FakeLLM(response="queryAgent")

    lg_utils_stub = ModuleType("restaurant_agent_core.services.lg_utils")
    lg_utils_stub.LLM_CLIENT = fake_llm
    monkeypatch.setitem(sys.modules, "restaurant_agent_core.services.lg_utils", lg_utils_stub)
    monkeypatch.setitem(
        sys.modules,
        "services",
        SimpleNamespace(lg_utils=lg_utils_stub),
    )

    # Force a clean import of the module under test
    sys.modules.pop("sfcs_agent.rest_agent.agents.router_agent", None)
    from sfcs_agent.rest_agent.agents import router_agent as module  # noqa: E402

    module._fake_llm = fake_llm
    yield module
    sys.modules.pop("sfcs_agent.rest_agent.agents.router_agent", None)


def _patch_response(module, response):
    """Replace the compiled router pipeline so its invoke returns {next_agent: response}."""

    class FixedChain:
        def __init__(self):
            self.last_payload = None

        def invoke(self, payload):
            self.last_payload = payload
            return {"next_agent": response}

    chain = FixedChain()
    module.router_agent = chain
    return chain


def test_run_router_agent_returns_query_agent(router_module):
    _patch_response(router_module, "queryAgent")

    assert router_module.run_router_agent("chicken biryani") == "queryAgent"


def test_run_router_agent_returns_takeaway_agent(router_module):
    _patch_response(router_module, "takeawayAgent")

    assert router_module.run_router_agent("I want to pick up an order") == "takeawayAgent"


def test_run_router_agent_returns_dinein_agent(router_module):
    _patch_response(router_module, "dineinAgent")

    assert router_module.run_router_agent("Book a table tonight") == "dineinAgent"


def test_run_router_agent_passes_human_message(router_module):
    chain = _patch_response(router_module, "queryAgent")

    router_module.run_router_agent("hello world")

    messages = chain.last_payload["messages"]
    assert len(messages) == 1
    assert messages[0].content == "hello world"


def test_router_typed_dict_lists_three_agents(router_module):
    # Router TypedDict literal union exposes the three known routing targets
    assert "queryAgent" in router_module.agents
    assert "takeawayAgent" in router_module.agents
    assert "dineinAgent" in router_module.agents
