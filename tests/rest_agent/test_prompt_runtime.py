"""Tests for state-aware system-prompt instructions."""

from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelRequest
from langgraph.runtime import Runtime

from restaurant_agent_runtime.rest_agent.prompt_runtime import (
    _retention_system_instruction,
    render_prompt_middleware,
)
from restaurant_agent_runtime.runtime import RestaurantChoice, RestaurantSelection


def _fake_master():
    return SimpleNamespace(
        house_number="1",
        building_name=None,
        street_name="High Street",
        city="London",
        postcode="E1 6AN",
        service_hours=SimpleNamespace(
            format_week=lambda: "Mon-Sun 9am-9pm",
            format_new_order_week=lambda: "Mon-Sun 9am-8:30pm",
        ),
    )


def _fake_context(*, restaurant_name="Elai", restaurant_selection=None):
    return SimpleNamespace(
        restaurant_name=restaurant_name,
        restaurant_contact_phone="01722656888",
        restaurant_master=_fake_master(),
        restaurant_selection=restaurant_selection,
    )


def _render(template: str, *, state: dict, context) -> str:
    middleware = render_prompt_middleware(template)
    request = ModelRequest(
        model=object(),
        messages=[],
        state=state,
        runtime=Runtime(context=context),
    )
    result = middleware.wrap_model_call(request, lambda req: req)
    return result.system_message.content


_TEMPLATE = "Currently selected restaurant: {selected_restaurant_name}"


def test_single_restaurant_app_renders_its_own_name_with_no_selection_config():
    content = _render(_TEMPLATE, state={}, context=_fake_context())

    assert content.startswith("Currently selected restaurant: Elai")


def test_pending_selection_never_names_a_brand():
    selection = RestaurantSelection(
        prompt="Which restaurant?",
        choices=(
            RestaurantChoice("ELAS", "Elai", "Elai Restaurant", "I want Elai"),
            RestaurantChoice(
                "CHKS", "Wings and Things", "Wings and Things", "I want Wings and Things"
            ),
        ),
    )
    content = _render(
        _TEMPLATE, state={}, context=_fake_context(restaurant_selection=selection)
    )

    assert content.startswith("Currently selected restaurant: not yet selected")
    assert "Elai" not in content
    assert "Wings and Things" not in content


def test_captured_selection_renders_the_chosen_brand():
    selection = RestaurantSelection(
        prompt="Which restaurant?",
        choices=(
            RestaurantChoice("ELAS", "Elai", "Elai Restaurant", "I want Elai"),
            RestaurantChoice(
                "CHKS", "Wings and Things", "Wings and Things", "I want Wings and Things"
            ),
        ),
    )
    content = _render(
        _TEMPLATE,
        state={"selected_rest_ref": "CHKS"},
        context=_fake_context(restaurant_selection=selection),
    )

    assert content.startswith("Currently selected restaurant: Wings and Things")


@pytest.mark.parametrize(
    ("active_agent", "expected_flow"),
    [
        ("delivery_agent", "Delivery flow is in motion."),
        ("takeaway_agent", "Takeaway flow is in motion."),
    ],
)
def test_retained_specialist_flow_is_a_strict_no_handover_instruction(
    active_agent, expected_flow
):
    instruction = _retention_system_instruction(
        {"active_agent": active_agent, "retain_thread": True}
    )

    assert expected_flow in instruction
    assert "Strictly avoid handover to other agents." in instruction


def test_paid_retained_delivery_injects_current_order_and_rider_pending_facts():
    instruction = _retention_system_instruction(
        {
            "active_agent": "delivery_agent",
            "retain_thread": True,
            "is_payment_successful": True,
            "is_delivery_rider_assigned": False,
            "is_delivery_picked_up": False,
        }
    )

    assert "payment confirmed" in instruction
    assert "allocation is pending" in instruction
    assert "Do not ask the customer to place another order" in instruction


def test_released_specialist_flow_allows_but_does_not_require_a_transfer():
    instruction = _retention_system_instruction(
        {"active_agent": "delivery_agent", "retain_thread": False}
    )

    assert "Transfers are allowed when the customer's intent requires one" in instruction
    assert "do not hand over merely because retention has been cleared" in instruction


def test_released_thread_informs_triage_that_handoffs_are_allowed():
    instruction = _retention_system_instruction(
        {"active_agent": "triage_agent", "retain_thread": False}
    )

    assert "SPECIALIST RETENTION RELEASED" in instruction
    assert "Transfers are allowed" in instruction


def test_missing_legacy_retention_does_not_inject_a_release_instruction():
    assert _retention_system_instruction({"active_agent": "delivery_agent"}) == ""
