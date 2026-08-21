"""Characterize the shared production Restaurant Agent graph."""

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_REST_AGENT_DIRS = (
    ("sfcs", REPO_ROOT / "apps/sfcs/src/sfcs_agent/rest_agent"),
    ("bnat", REPO_ROOT / "apps/bnat/src/bnat_agent/rest_agent"),
    ("elas", REPO_ROOT / "apps/elas/src/elas_agent/rest_agent"),
)
AGENT_IMPLEMENTATIONS = (
    (
        "runtime",
        REPO_ROOT
        / "packages/restaurant-agent-runtime/src/restaurant_agent_runtime/rest_agent/agents",
    ),
)

STANDARD_AGENTS = ("triage_agent", "delivery_agent", "takeaway_agent")
STANDARD_TOOLS = {
    "triage.py": (
        "send_welcome_message",
        "ask_user_to_select_service",
        "ask_user_to_select_enquiry",
        "capture_marketing_consent",
        "submit_restaurant_feedback",
        "terminate_conversation",
        "transfer_to_delivery",
        "transfer_to_takeaway",
    ),
    "delivery.py": (
        "send_welcome_msg",
        "answer_general_query",
        "confirm_delivery_address",
        "capture_delivery_address",
        "update_address_of_existing_user",
        "calculate_min_order_value",
        "send_restaurant_menu_tool",
        "verify_if_payment_complete",
        "update_customer",
        "check_delivery_driver_allocation_status",
        "send_rider_live_location_link",
        "request_rider_location",
        "transfer_to_takeaway",
        "transfer_to_triage",
    ),
    "takeaway.py": (
        "verify_if_payment_complete",
        "update_customer",
        "send_takeaway_menu_tool",
        "transfer_to_delivery",
        "transfer_to_triage",
    ),
}
TOOL_VARIABLES = {
    "triage.py": "triage_tools",
    "delivery.py": "delivery_tools",
    "takeaway.py": "takeaway_tools",
}
PROMPT_FILES = {
    "triage.py": "triage_agent_prompt.md",
    "delivery.py": "delivery_multiagent_prompt.md",
    "takeaway.py": "takeaway_agent_prompt.md",
}
BUILD_FUNCTIONS = {
    "triage.py": "build_triage_agent",
    "delivery.py": "build_delivery_agent",
    "takeaway.py": "build_takeaway_agent",
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _expression_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    raise AssertionError(f"expected a name or string, got {ast.dump(expression)}")


def _assigned_name_list(tree: ast.Module, variable: str) -> tuple[str, ...]:
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.List):
            continue
        if any(isinstance(target, ast.Name) and target.id == variable for target in statement.targets):
            return tuple(_expression_name(item) for item in statement.value.elts)
    raise AssertionError(f"could not find list assignment for {variable}")


def test_production_graph_has_the_standard_nodes_and_routes():
    """Characterize the graph shape via the real builder, not source text.

    `build_multi_agent_graph` gained an optional `dinein_agent_node` argument
    (config-gated on an app supplying a dine-in prompt). AST parsing of the
    function body can no longer distinguish "the unconditional baseline" from
    "the dine-in-configured graph", since both come from the same source with
    a runtime branch — so this test builds the real StateGraph both ways and
    inspects the constructed object, which is what actually determines
    behavior for every app.
    """
    from langchain_core.messages import AIMessage
    from restaurant_agent_runtime.rest_agent.agents.multi_agent import (
        DINEIN_AGENT,
        build_multi_agent_graph,
        route_after_agent,
        route_initial,
    )

    def _node(_state):
        return _state

    baseline = build_multi_agent_graph(_node, _node, _node)
    assert set(baseline.nodes.keys()) == set(STANDARD_AGENTS)

    with_dinein = build_multi_agent_graph(_node, _node, _node, dinein_agent_node=_node)
    assert set(with_dinein.nodes.keys()) == set(STANDARD_AGENTS) | {DINEIN_AGENT}

    # Every app, configured or not, still defaults to triage and still ends
    # on a final AIMessage without tool calls.
    assert route_initial({}) == "triage_agent"
    assert route_initial({"active_agent": "delivery_agent"}) == "delivery_agent"
    assert route_after_agent({"messages": [AIMessage("done")]}) == "__end__"

    # dinein_agent is unreachable unless the app explicitly widens valid_agents
    # (mirroring what `_build_graph` does only when `prompts.dinein` is set).
    assert route_initial({"active_agent": DINEIN_AGENT}) == "triage_agent"
    assert (
        route_initial(
            {"active_agent": DINEIN_AGENT},
            valid_agents=frozenset({*STANDARD_AGENTS, DINEIN_AGENT}),
        )
        == DINEIN_AGENT
    )


@pytest.mark.parametrize(("app_name", "agent_dir"), AGENT_IMPLEMENTATIONS)
def test_standard_agent_tool_order_is_unchanged(app_name, agent_dir):
    actual = {
        filename: _assigned_name_list(_parse(agent_dir / filename), variable)
        for filename, variable in TOOL_VARIABLES.items()
    }
    assert actual == STANDARD_TOOLS, app_name


@pytest.mark.parametrize(("app_name", "rest_agent_dir"), APP_REST_AGENT_DIRS)
def test_each_app_owns_complete_non_empty_prompts(app_name, rest_agent_dir):
    recipe_source = (rest_agent_dir / "agent_recipe.py").read_text()
    for prompt_filename in PROMPT_FILES.values():
        prompt_path = rest_agent_dir / "prompts" / prompt_filename
        assert prompt_path.read_text().strip(), (app_name, prompt_filename)
        assert prompt_filename in recipe_source


@pytest.mark.parametrize(("app_name", "rest_agent_dir"), APP_REST_AGENT_DIRS)
def test_specialist_prompts_keep_retained_orders_with_the_specialist(
    app_name, rest_agent_dir
):
    prompt_dir = rest_agent_dir / "prompts"
    for prompt_filename in (
        "delivery_multiagent_prompt.md",
        "takeaway_agent_prompt.md",
    ):
        prompt = (prompt_dir / prompt_filename).read_text()
        assert "`retain_thread=True`" in prompt, (app_name, prompt_filename)
        assert "`update_customer(message=...)`" in prompt, (app_name, prompt_filename)
        assert "strictly avoid handover to other agents" in prompt, (
            app_name,
            prompt_filename,
        )


@pytest.mark.parametrize(("app_name", "rest_agent_dir"), APP_REST_AGENT_DIRS)
def test_customer_support_prompt_contract_is_consistent(app_name, rest_agent_dir):
    prompt_dir = rest_agent_dir / "prompts"
    delivery = (prompt_dir / "delivery_multiagent_prompt.md").read_text()
    takeaway = (prompt_dir / "takeaway_agent_prompt.md").read_text()
    triage = (prompt_dir / "triage_agent_prompt.md").read_text()

    assert "Delivery time depends on traffic and the distance to your address." in delivery
    assert "We will share the rider’s location with you once it’s available." in delivery
    assert "Never claim that a refund has been issued" in delivery
    assert "Your refund has been issued. It may take a few hours to a couple of days" not in delivery
    assert "current collection order first" in takeaway
    assert "Never claim that a refund has been issued" in triage
    assert "Your refund has been issued. It may take a few hours to a couple of days" not in triage


@pytest.mark.parametrize(("app_name", "agent_dir"), AGENT_IMPLEMENTATIONS)
def test_agent_construction_requires_explicit_model_and_prompt(app_name, agent_dir):
    for agent_filename, build_function in BUILD_FUNCTIONS.items():
        tree = _parse(agent_dir / agent_filename)
        top_level_names = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        top_level_assignments = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        imported_names = {
            alias.name
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }

        assert build_function in top_level_names, (app_name, agent_filename)
        assert "agent" not in top_level_assignments, (app_name, agent_filename)
        assert "llm_settings" not in imported_names, (app_name, agent_filename)
