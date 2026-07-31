"""Tests for the canonical pure FoodOrder aggregate model."""

import pytest
from pydantic import ValidationError

from restaurant_agent_runtime.services.order_management.food_order_pymodel import (
    FoodOrder,
)


def test_food_order_validates_active_boundary_payload():
    order = FoodOrder(
        order_id="ORD-1",
        order_number="SFCS-ORD-1",
        recipient="447000000001",
        thread_id="thread-1",
        action="delivery",
        total_price=20.0,
        final_order_value=24.5,
        payment_status="requires_capture",
    )

    assert order.order_id == "ORD-1"
    assert order.final_order_value == 24.5
    assert order.service_charge is None


def test_food_order_requires_aggregate_identity():
    with pytest.raises(ValidationError):
        FoodOrder.model_validate(
            {
                "recipient": "447000000001",
                "thread_id": "thread-1",
                "action": "delivery",
                "total_price": 20.0,
                "payment_status": "requires_payment",
            }
        )
