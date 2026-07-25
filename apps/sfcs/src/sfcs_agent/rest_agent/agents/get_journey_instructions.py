# %%
import ast
import operator

# Safe evaluation environment for entry conditions
SAFE_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
}


def safe_eval_condition(expr: str, state: dict) -> bool:
    """
    Safely evaluate expressions like:
    - state.customer_address is None
    - state.is_payment_successful is False
    - state.min_order_value is not None
    """

    # Convert dotted access (state.xxx) into dictionary lookups
    local_state = {k: v for k, v in state.items()}

    # Turn "state.xxx" into "local_state['xxx']"
    expr = (
        expr.replace("state.", "local_state.get('")
        .replace(" is None", "') is None")
        .replace(" is not None", "') is not None")
        .replace(" is True", "') is True")
        .replace(" is False", "') is False")
    )

    try:
        # Evaluate in a restricted namespace
        return eval(expr, {"__builtins__": {}}, {"local_state": local_state})
    except Exception:
        return False


def next_node_from_state(workflow: dict, state: dict):
    """
    Determine the next workflow node based on the DAG and current state.
    """

    nodes = workflow.get("nodes", {})

    for node_name, node in nodes.items():
        entry_cond = node.get("entry_condition")
        node_kind = node.get("kind")

        # Evaluate entry condition
        if entry_cond and safe_eval_condition(entry_cond, state):
            # ---- Handle decision nodes ----
            if node_kind == "decision":
                transitions = node.get("transitions", [])
                for t in transitions:
                    cond = t.get("condition")
                    if safe_eval_condition(cond, state):
                        return {
                            "node": t["next"],
                            "reason": f"Transition matched: {cond}",
                            "type": "decision",
                        }

                return {
                    "node": None,
                    "reason": f"No transitions matched for decision node {node_name}.",
                    "type": "decision",
                }

            # ---- Handle tool or user-action nodes ----
            return {
                "node": node_name,
                "reason": f"entry_condition satisfied: {entry_cond}",
                "type": node_kind,
            }

    # Nothing matches → journey completed or unknown state
    return {
        "node": None,
        "reason": "No workflow node matches this state.",
        "type": "terminal",
    }


# %%
workflow = {
    "workflow_name": "delivery_journey",
    "start_node": "capture_delivery_address",
    "nodes": {
        "capture_delivery_address": {
            "kind": "tool_step",
            "tool_name": "capture_delivery_address",
            "entry_condition": "state.customer_address is None",
            "action": "Call tool `capture_delivery_address` to capture customer delivery address.",
            "next": ["confirm_delivery_address"],
        },
        "confirm_delivery_address": {
            "kind": "tool_step",
            "tool_name": "confirm_delivery_address",
            "entry_condition": "state.customer_address is not None and state.is_delivery_address_confirmed is False",
            "action": "Call tool `confirm_delivery_address` to confirm delivery address with the user.",
            "next": ["calculate_min_order_value", "outside_delivery_area_guard"],
        },
        "calculate_min_order_value": {
            "kind": "tool_step",
            "tool_name": "calculate_min_order_value",
            "entry_condition": "state.is_delivery_address_confirmed is True and state.min_order_value is None",
            "action": "Delivery address confirmed. Calculate the minimum order value using `calculate_min_order_value`.",
            "next": ["outside_delivery_area_guard"],
        },
        "outside_delivery_area_guard": {
            "kind": "decision",
            "entry_condition": "state.is_delivery_address_confirmed is True and state.min_order_value is not None",
            "transitions": [
                {
                    "condition": "state.is_outside_delivery_area is True",
                    "next": "outside_delivery_area_terminal",
                },
                {
                    "condition": "state.is_outside_delivery_area is False",
                    "next": "request_order_placement",
                },
            ],
            "note": "If the confirmed address is outside delivery area, stop the journey; otherwise proceed to order placement.",
        },
        "outside_delivery_area_terminal": {
            "kind": "terminal",
            "entry_condition": "state.is_outside_delivery_area is True",
            "action": "Inform the user that the delivery address is outside the delivery area and do not proceed to further steps.",
            "next": [],
        },
        "request_order_placement": {
            "kind": "user_action_step",
            "tool_name": "send_restaurant_menu_tool",
            "entry_condition": "state.is_outside_delivery_area is False and state.min_order_value is not None and state.order_id is None",
            "action": "Delivery address confirmed and minimum order value calculated. Send the menu using `send_restaurant_menu_tool` and ask the user to place an order using the catalog button.",
            "next": ["verify_payment"],
        },
        "verify_payment": {
            "kind": "tool_step",
            "tool_name": "verify_if_payment_complete",
            "entry_condition": "state.order_id is not None and state.is_payment_successful is False",
            "action": "Order placed. Payment handled externally. Verify payment status using `verify_if_payment_complete`.",
            "next": ["wait_for_driver_allocation"],
        },
        "wait_for_driver_allocation": {
            "kind": "tool_step",
            "tool_name": "check_delivery_driver_allocation_status",
            "entry_condition": "state.order_id is not None and state.is_payment_successful is True and state.is_delivery_rider_assigned is False",
            "action": "Payment completed. Inform the user that we are looking for available delivery drivers.",
            "next": ["driver_assigned_wait_for_pickup"],
        },
        "driver_assigned_wait_for_pickup": {
            "kind": "tool_step",
            "tool_name": "update_customer",
            "entry_condition": "state.is_delivery_rider_assigned is True and state.rider_live_location_url is None",
            "action": "Driver assigned but food not yet collected. Use `update_customer` to inform the customer.",
            "next": ["driver_picked_up_share_live_location"],
        },
        "driver_picked_up_share_live_location": {
            "kind": "tool_step",
            "tool_name": "send_rider_live_location_link",
            "entry_condition": "state.is_delivery_rider_assigned is True and state.is_delivery_picked_up is True and state.rider_live_location_url is not None",
            "action": "Driver has collected the food. Share live location using `send_rider_live_location_link`.",
            "next": ["journey_complete"],
        },
        "journey_complete": {
            "kind": "terminal",
            "entry_condition": "state.is_delivery_picked_up is True and state.order_id is not None",
            "action": "Journey complete. Continue assisting the user with updates as needed.",
            "next": [],
        },
    },
}


# %%
def get_journey_instructions_from_dag(state):
    node_info = next_node_from_state(workflow, state)

    node = node_info["node"]

    if node is None:
        return "Journey complete or no valid next step."

    step = workflow["nodes"][node]
    return step["action"]


# %%
sample_state = {
    "messages": [],
    "customer_address": None,
    "is_delivery_address_confirmed": True,
    "min_order_value": 8.5,
    "is_outside_delivery_area": False,
    "order_id": None,
    "is_payment_successful": False,
    "is_delivery_rider_assigned": False,
    "rider_live_location_url": None,
    "is_delivery_picked_up": False,
}

# %%

get_journey_instructions_from_dag(sample_state)
