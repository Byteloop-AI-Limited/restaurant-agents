from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text()


def _parse(rel_path: str) -> ast.AST:
    return ast.parse(_read(rel_path))


def _function_names(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assigned_list_names(tree: ast.AST, target_name: str) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == target_name:
                if not isinstance(node.value, ast.List):
                    raise AssertionError(f"{target_name} is not assigned from a list")
                return [
                    elt.id
                    for elt in node.value.elts
                    if isinstance(elt, ast.Name)
                ]
    raise AssertionError(f"{target_name} assignment not found")


def test_agent_runner_bootstrap_seeds_rest_ref_and_correct_tool_name():
    source = _read("sfcs_agent.rest_agent/agent_runner.py")

    assert '"rest_ref": project_settings.rest_ref.lower()' in source
    assert "Call tool `send_welcome_message`" in source
    assert "Call tool `send_welcome_msg`" not in source


def test_triage_tool_surface_matches_single_restaurant_flow():
    tree = _parse("sfcs_agent.rest_agent/agents/triage.py")
    functions = _function_names(tree)

    assert "ask_user_to_select_restaurant" not in functions
    assert "capture_restaurant_selected" not in functions

    assert _assigned_list_names(tree, "triage_tools") == [
        "send_welcome_message",
        "ask_user_to_select_service",
        "capture_marketing_consent",
        "terminate_conversation",
        "transfer_to_delivery",
        "transfer_to_takeaway",
        "transfer_to_dinein",
    ]


def test_sender_and_callbacks_no_longer_define_select_rest_ref_flow():
    sender_source = _read("sfcs_agent.rest_agent/agent_wa_senders.py")
    callback_source = _read("restaurant_agent_core.watomation/on_callback_handler.py")
    callback_tree = _parse("restaurant_agent_core.watomation/on_callback_handler.py")

    assert "select_rest_ref_wa_send" not in sender_source
    assert "normalized_rest_ref = str(rest_ref).lower()" in sender_source
    assert "select_rest_ref_handler" not in _function_names(callback_tree)
    assert (
        'callback_data_dict.get("rest_ref") or project_settings.rest_ref.lower()'
        in callback_source
    )


def test_callback_registration_only_keeps_select_service_flow():
    source = _read("restaurant_agent_core.watomation/fapp.py")

    assert "/SelectService" in source
    assert "/SelectRestRef" not in source
    assert "select_rest_ref_handler" not in source


def test_triage_prompt_describes_single_restaurant_behavior():
    prompt = _read("sfcs_agent.rest_agent/agents/prompts/triage_agent_prompt.md")

    assert "serving one configured restaurant" in prompt
    assert "Do not ask the user to choose a restaurant." in prompt
    assert "ask_user_to_select_restaurant" not in prompt
    assert "capture_restaurant_selected" not in prompt
