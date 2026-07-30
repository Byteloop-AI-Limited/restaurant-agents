"""
Unit tests for WhatsApp order receipt formatting helpers
    . Loads receipt helpers with stubbed FoodOrder and config dependencies
    . Covers item formatting with list, string, empty, and non-iterable modifications
    . Covers customer and restaurant receipt output and missing-data errors
  Functions/Classes:
    . receipt_module
    . make_food_order
    . test_format_order_item_lines_handles_modifications
    . test_customer_receipt_includes_charges_total_and_notes
    . test_restaurant_receipt_uses_food_total_and_kitchen_header
    . test_receipt_raises_when_no_items
"""

from types import ModuleType

import pytest

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


@pytest.fixture
def receipt_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={
            "order_item": [
                {
                    "product_name": "Paneer Curry",
                    "quantity": 2,
                    "price": 8.5,
                    "modifications": ["extra spicy", "no onions"],
                }
            ]
        }
    )

    pricing_module = ModuleType("restaurant_agent_runtime.services.pricing_ms")
    pricing_module.get_final_order_value = lambda **kwargs: {}

    food_order_module = load_module(
        "test_receipt_food_order_pymodel_module",
        "restaurant_agent_runtime.services/order_management/food_order_pymodel.py",
        monkeypatch,
        {"config": config_stub, "restaurant_agent_runtime.services.pricing_ms": pricing_module},
    )
    order_db_ops_new_module = load_module(
        "test_receipt_order_db_ops_new_module",
        "restaurant_agent_runtime.services/order_management/order_db_ops_new.py",
        monkeypatch,
        {"config": config_stub},
    )

    module = load_module(
        "test_food_order_receipt_module",
        "restaurant_agent_runtime.services/order_management/food_order_reciept.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_runtime.services.order_management.food_order_pymodel": food_order_module,
            "restaurant_agent_runtime.services.order_management.order_db_ops_new": order_db_ops_new_module,
        },
    )
    module._config_stub = config_stub
    return module


def make_food_order(module, **overrides):
    data = {
        "order_id": "ORD-1",
        "order_number": "ELAS-1",
        "recipient": "447000000001",
        "thread_id": "thread-1",
        "action": "delivery",
        "total_price": 17.0,
        "final_order_value": 22.5,
        "rest_cost": 14.0,
        "service_charge": 2.0,
        "delivery_fee": 3.5,
        "small_order_fee": 0.0,
        "commission_rate": 0.2,
        "payment_status": "requires_payment",
        "notes": "Ring bell",
    }
    data.update(overrides)
    return module.FoodOrder(**data)


def test_format_order_item_lines_handles_modifications(receipt_module):
    lines = receipt_module._format_order_item_lines(
        [
            {"quantity": 2, "product_name": "Curry", "price": 5.0, "modifications": "hot"},
            {"quantity": 1, "product_name": "Rice", "price": 3.0, "modifications": [" ", "plain"]},
            {"quantity": 1, "product_name": "Naan", "price": 2.0, "modifications": 123},
        ]
    )

    assert lines == [
        "*• 2 × Curry  –  £10.00*",
        "   ↳ _hot_",
        "*• 1 × Rice  –  £3.00*",
        "   ↳ _plain_",
        "*• 1 × Naan  –  £2.00*",
        "   ↳ _123_",
    ]


def test_customer_receipt_includes_charges_total_and_notes(receipt_module):
    header, text = receipt_module.build_wa_order_reciept_for_cust(
        food_order=make_food_order(receipt_module)
    )

    assert header == "Order #ELAS-1"
    assert "*• 2 × Paneer Curry  –  £17.00*" in text
    assert "Service charge: £2.00" in text
    assert "Delivery fee: £3.50" in text
    assert "*Total:* £22.50" in text
    assert "_Ring bell_" in text


def test_restaurant_receipt_uses_food_total_and_kitchen_header(receipt_module):
    order_item = receipt_module.OrderItem(
        order_id="ORD-1",
        sku="paneer",
        quantity=2,
        price=8.5,
        product_name="Paneer Curry",
        modifications=["extra spicy"],
    )

    header, text = receipt_module.build_wa_order_reciept_for_rest(
        food_order=make_food_order(receipt_module, small_order_fee=1.0),
        order_items=[order_item],
    )

    assert header == "Order #ELAS-1 (Kitchen)"
    assert "*• 2 × Paneer Curry  –  £17.00*" in text
    assert "Small order fee: £1.00" in text
    assert "*Total:* £17.00" in text


def test_receipt_raises_when_no_items(receipt_module):
    receipt_module.client_ordelo = FakeSupabaseClient(table_data={"order_item": []})

    with pytest.raises(ValueError, match="No order_items"):
        receipt_module.build_wa_order_reciept_for_cust(
            food_order=make_food_order(receipt_module)
        )
