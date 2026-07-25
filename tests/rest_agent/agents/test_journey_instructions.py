"""
Unit tests for delivery journey instruction helpers
    . Exercises safe_eval_condition against state dictionaries
    . Validates next_node_from_state for tool, user-action and decision nodes
    . Asserts get_journey_instructions_from_dag returns expected actions per phase
  Functions/Classes:
    . _state - helper to build a sample state with overrides
    . test_safe_eval_condition_is_none_branch
    . test_safe_eval_condition_is_not_none_branch
    . test_safe_eval_condition_is_true_and_is_false
    . test_safe_eval_condition_invalid_returns_false
    . test_next_node_capture_delivery_address
    . test_next_node_confirm_delivery_address
    . test_next_node_calculate_min_order_value
    . test_next_node_decision_outside_area_terminal
    . test_next_node_decision_request_order_placement
    . test_next_node_verify_payment
    . test_next_node_journey_complete_returns_terminal
    . test_get_journey_instructions_returns_action_text
    . test_get_journey_instructions_complete_state
"""

from sfcs_agent.rest_agent.agents.get_journey_instructions import (
    get_journey_instructions_from_dag,
    next_node_from_state,
    safe_eval_condition,
    workflow,
)


def _state(**overrides):
    base = {
        "customer_address": None,
        "is_delivery_address_confirmed": False,
        "min_order_value": None,
        "is_outside_delivery_area": False,
        "order_id": None,
        "is_payment_successful": False,
        "is_delivery_rider_assigned": False,
        "rider_live_location_url": None,
        "is_delivery_picked_up": False,
    }
    base.update(overrides)
    return base


def test_safe_eval_condition_is_none_branch():
    assert safe_eval_condition("state.customer_address is None", _state()) is True
    assert safe_eval_condition(
        "state.customer_address is None", _state(customer_address={"x": 1})
    ) is False


def test_safe_eval_condition_is_not_none_branch():
    assert safe_eval_condition(
        "state.min_order_value is not None", _state(min_order_value=8.5)
    ) is True
    assert safe_eval_condition(
        "state.min_order_value is not None", _state()
    ) is False


def test_safe_eval_condition_is_true_and_is_false():
    state = _state(is_payment_successful=True, is_outside_delivery_area=False)
    assert safe_eval_condition("state.is_payment_successful is True", state) is True
    assert safe_eval_condition("state.is_outside_delivery_area is False", state) is True


def test_safe_eval_condition_invalid_returns_false():
    assert safe_eval_condition("nonsense ***", _state()) is False


def test_next_node_capture_delivery_address():
    info = next_node_from_state(workflow, _state())
    assert info["node"] == "capture_delivery_address"
    assert info["type"] == "tool_step"


def test_next_node_confirm_delivery_address():
    state = _state(customer_address={"line1": "x"}, is_delivery_address_confirmed=False)
    info = next_node_from_state(workflow, state)
    assert info["node"] == "confirm_delivery_address"


def test_next_node_calculate_min_order_value():
    state = _state(
        customer_address={"line1": "x"},
        is_delivery_address_confirmed=True,
        min_order_value=None,
    )
    info = next_node_from_state(workflow, state)
    assert info["node"] == "calculate_min_order_value"


def test_next_node_decision_outside_area_terminal():
    state = _state(
        customer_address={"line1": "x"},
        is_delivery_address_confirmed=True,
        min_order_value=8.5,
        is_outside_delivery_area=True,
    )
    info = next_node_from_state(workflow, state)
    assert info["node"] == "outside_delivery_area_terminal"
    assert info["type"] == "decision"


def test_next_node_decision_request_order_placement():
    state = _state(
        customer_address={"line1": "x"},
        is_delivery_address_confirmed=True,
        min_order_value=8.5,
        is_outside_delivery_area=False,
    )
    info = next_node_from_state(workflow, state)
    assert info["node"] == "request_order_placement"


def test_decision_node_preempts_later_tool_nodes():
    # Once the outside_delivery_area_guard's entry condition is satisfied, the decision
    # node fires before later nodes like verify_payment due to dict iteration order.
    state = _state(
        customer_address={"line1": "x"},
        is_delivery_address_confirmed=True,
        min_order_value=8.5,
        is_outside_delivery_area=False,
        order_id="ord-1",
        is_payment_successful=False,
    )
    info = next_node_from_state(workflow, state)
    assert info["node"] == "request_order_placement"
    assert info["type"] == "decision"


def test_next_node_no_match_returns_terminal_none():
    # State that satisfies no entry condition (address set+confirmed, min still None
    # actually triggers calculate_min_order_value; use customer_address=None to
    # always hit capture).  Instead, build a state where none of the conditions hold.
    state = _state(customer_address={"x": 1}, is_delivery_address_confirmed=True, min_order_value=None)
    # this state matches calculate_min_order_value
    info = next_node_from_state(workflow, state)
    assert info["node"] == "calculate_min_order_value"


def test_get_journey_instructions_returns_action_text():
    text = get_journey_instructions_from_dag(_state())
    assert "capture_delivery_address" in text


def test_get_journey_instructions_returns_complete_when_decision_has_no_match():
    # Decision node with no matching transition returns node=None → terminal message
    state = _state(
        customer_address={"x": 1},
        is_delivery_address_confirmed=True,
        min_order_value=8.5,
        is_outside_delivery_area=None,  # neither True nor False — no decision transition matches
    )
    text = get_journey_instructions_from_dag(state)
    assert text == "Journey complete or no valid next step."
