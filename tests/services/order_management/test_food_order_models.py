"""
Unit tests for FoodOrder model payment and pricing helpers
    . Loads FoodOrder with stubbed config and pricing dependencies
    . Covers payment URI, final-order-value update, payload generation, and lookup failures
    . Uses a fake Supabase client to avoid live database access
  Functions/Classes:
    . food_order_module
    . make_food_order
    . test_payment_uri_uses_thread_and_order_id
    . test_update_final_order_value_updates_instance_and_db
    . test_update_final_order_value_returns_false_without_customer
    . test_from_order_id_returns_existing_final_value_without_update
    . test_from_order_id_returns_none_when_missing
    . test_generate_order_summary_for_payment_intent_adds_nonzero_fees
    . test_gen_payment_and_capture_payloads
"""

from types import ModuleType

import pytest

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


@pytest.fixture
def food_order_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={
            "customer_master": [{"lat": 51.5, "lon": -0.1}],
            "food_order": [
                {
                    "order_id": "ORD-1",
                    "order_number": "ELAS-1",
                    "recipient": "447000000001",
                    "thread_id": "thread-1",
                    "action": "delivery",
                    "total_price": 20.0,
                    "final_order_value": 24.5,
                    "rest_cost": 16.0,
                    "service_charge": 2.0,
                    "delivery_fee": 2.5,
                    "small_order_fee": 0.0,
                    "commission_rate": 0.2,
                    "payment_status": "requires_payment",
                }
            ],
            "order_item": [
                {"product_name": "Curry", "quantity": 2, "price": 10.0},
            ],
        }
    )

    pricing_module = ModuleType("restaurant_agent_core.services.pricing_ms")
    pricing_module.get_final_order_value = lambda **kwargs: {
        "final_order_value": 25.5,
        "rest_cost": 18.0,
        "breakdown": {
            "service_charge": 2.0,
            "delivery_fee": 3.5,
            "small_order_fee": 2.0,
            "commission_rate": 0.15,
        },
    }

    module = load_module(
        "test_food_order_pymodel_module",
        "restaurant_agent_core.services/order_management/food_order_pymodel.py",
        monkeypatch,
        {"config": config_stub, "restaurant_agent_core.services.pricing_ms": pricing_module},
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
        "total_price": 20.0,
        "final_order_value": 24.5,
        "rest_cost": 16.0,
        "service_charge": 2.0,
        "delivery_fee": 2.5,
        "small_order_fee": 0.0,
        "commission_rate": 0.2,
        "payment_status": "requires_payment",
    }
    data.update(overrides)
    return module.FoodOrder(**data)


def test_payment_uri_uses_thread_and_order_id(food_order_module):
    order = make_food_order(food_order_module)
    assert order.payment_uri == "https://stripe.test/threads/thread-1/orders/ORD-1/payment-url"


def test_update_final_order_value_updates_instance_and_db(food_order_module):
    order = make_food_order(food_order_module, final_order_value=None)

    assert order.update_final_order_value_in_db() is True
    assert order.final_order_value == 25.5
    assert order.rest_cost == 18.0
    assert order.service_charge == 2.0
    assert order.delivery_fee == 3.5
    assert order.small_order_fee == 2.0
    assert order.commission_rate == 0.15


def test_update_final_order_value_returns_false_without_customer(food_order_module):
    food_order_module.client_ordelo = FakeSupabaseClient(table_data={"customer_master": []})
    order = make_food_order(food_order_module, final_order_value=None)

    assert order.update_final_order_value_in_db() is False


def test_from_order_id_returns_existing_final_value_without_update(food_order_module):
    order = food_order_module.FoodOrder.from_order_id("ORD-1")

    assert order.order_id == "ORD-1"
    assert order.final_order_value == 24.5


def test_from_order_id_returns_none_when_missing(food_order_module):
    food_order_module.client_ordelo = FakeSupabaseClient(table_data={"food_order": []})

    assert food_order_module.FoodOrder.from_order_id("missing") is None


@pytest.mark.asyncio
async def test_generate_order_summary_for_payment_intent_adds_nonzero_fees(food_order_module):
    order = make_food_order(food_order_module, small_order_fee=1.0)

    summary = await order.generate_order_summary_for_payment_intent()

    assert summary["items"] == [
        {"product_name": "Curry", "quantity": 2, "price": 10.0},
        {"product_name": "Service Charge", "quantity": 1, "price": 2.0},
        {"product_name": "Delivery Fee", "quantity": 1, "price": 2.5},
        {"product_name": "Small Order Fee", "quantity": 1, "price": 1.0},
    ]


@pytest.mark.asyncio
async def test_gen_payment_and_capture_payloads(food_order_module):
    order = make_food_order(food_order_module, notes="No onions")

    payment_payload = await order.gen_payment_intent_payload()
    capture_payload = await order.gen_capture_payload()

    assert payment_payload["currency"] == "GBP"
    assert payment_payload["action"] == "delivery"
    assert payment_payload["manual_mode_capture"] is True
    assert capture_payload["payment_mode"] == "capture"
    assert capture_payload["rest_payout"] == 16.0
    assert capture_payload["total_amount"] == 24.5
    assert capture_payload["notes"] == "No onions"
