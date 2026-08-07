"""SFCS composition tests for the shared Restaurant Agent adapter."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from restaurant_agent_runtime.rest_agent.prompts import RestaurantPrompts


def test_sfcs_entrypoint_uses_shared_agent_runtime():
    source = (Path(__file__).resolve().parents[1] / "src/sfcs_agent/main.py").read_text()

    assert "GRAPH_ADAPTER_FACTORY" in source
    assert "restaurant_agent_runtime.rest_agent.agent_wa_senders" in source
    assert "sfcs_agent.rest_agent.agent_runner" not in source
    assert "sfcs_agent.rest_agent.agent_wa_senders" not in source


def test_sfcs_prompts_require_eager_purpose_built_tool_use():
    prompt_dir = Path(__file__).resolve().parents[1] / "src/sfcs_agent/rest_agent/prompts"

    assert "**EAGER TOOL USE:**" in (prompt_dir / "triage_agent_prompt.md").read_text()
    delivery_prompt = (prompt_dir / "delivery_multiagent_prompt.md").read_text()
    assert "immediately call `confirm_delivery_address`" in delivery_prompt
    assert "immediately call `capture_delivery_address`" in delivery_prompt
    assert "immediately call `calculate_min_order_value`" in delivery_prompt
    assert "**EAGER TOOL USE:**" in (prompt_dir / "takeaway_agent_prompt.md").read_text()


def test_sfcs_recipe_binds_its_prompts_and_exact_runtime(monkeypatch):
    class FakeRestaurantGraphAdapter:
        def __init__(self, runtime, *, prompts):
            self.runtime = runtime
            self.prompts = prompts

    core_stub = ModuleType("restaurant_agent_runtime.rest_agent")
    core_stub.RestaurantGraphAdapter = FakeRestaurantGraphAdapter
    core_stub.RestaurantPrompts = RestaurantPrompts
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.rest_agent", core_stub)

    recipe_path = (
        Path(__file__).resolve().parents[1]
        / "src/sfcs_agent/rest_agent/agent_recipe.py"
    )
    spec = importlib.util.spec_from_file_location("sfcs_recipe_under_test", recipe_path)
    recipe = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(recipe)

    async_wa_client = object()
    runtime = SimpleNamespace(async_wa_client=async_wa_client)
    adapter = recipe.GRAPH_ADAPTER_FACTORY(runtime)

    assert adapter.runtime is runtime
    assert adapter.runtime.async_wa_client is async_wa_client
    assert adapter.prompts == RestaurantPrompts(
        triage=(recipe.PROMPT_DIR / "triage_agent_prompt.md").read_text(),
        delivery=(recipe.PROMPT_DIR / "delivery_multiagent_prompt.md").read_text(),
        takeaway=(recipe.PROMPT_DIR / "takeaway_agent_prompt.md").read_text(),
    )
