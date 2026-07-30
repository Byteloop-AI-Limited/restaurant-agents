"""
Unit tests for legacy order database operations that do not require live database access
    . Loads order_db_ops with a stubbed config module to avoid external clients
    . Covers order-id generation, order item conversion, total calculation, and summaries
    . Verifies current legacy behavior separately from newer order_db_ops_new behavior
  Functions/Classes:
    . test_food_order_model_generates_order_id
    . test_food_order_model_rejects_invalid_recipient_tail
    . test_get_order_total_uses_legacy_price_only_behavior
    . test_create_order_items_from_order_maps_product_names
    . test_create_order_summary_formats_payment_payload
"""

import pytest

from tests._stubs.loader import load_module


@pytest.fixture
def order_db_ops(monkeypatch):
    return load_module(
        "test_order_db_ops_legacy_module",
        "restaurant_agent_runtime.services/order_management/order_db_ops.py",
        monkeypatch,
    )


def test_food_order_model_generates_order_id(order_db_ops):
    order = order_db_ops.FoodOrderModel(
        recipient="447424331234",
        thread_id="thread-1",
        seq_id=7,
        total_amount=19.9,
        order_dt="2026-05-09",
    )

    code, seq = order.order_id.split("-")
    assert len(code) == 4
    assert code.isupper()
    assert seq == "7"


def test_food_order_model_rejects_invalid_recipient_tail(order_db_ops):
    with pytest.raises(ValueError, match="4-digit"):
        order_db_ops.FoodOrderModel(
            recipient="abc",
            thread_id="thread-1",
            seq_id=1,
            total_amount=1.0,
        )


def test_get_order_total_uses_legacy_price_only_behavior(order_db_ops, sample_wa_order):
    assert order_db_ops.get_order_total(sample_wa_order) == 19.9


@pytest.mark.asyncio
async def test_create_order_items_from_order_maps_product_names(order_db_ops, sample_wa_order, mock_sku_product_map):
    items = await order_db_ops.create_order_items_from_order(
        sample_wa_order,
        order_id="ORD-1",
        sku_nam_map=mock_sku_product_map,
    )

    assert [item.product_name for item in items] == ["Chilli Chicken", "Aloo Gobi"]
    assert [item.order_id for item in items] == ["ORD-1", "ORD-1"]


@pytest.mark.asyncio
async def test_create_order_summary_formats_payment_payload(order_db_ops):
    summary = await order_db_ops.create_order_summary(
        [
            {
                "order_id": "ORD-1",
                "order_type": "Paid Collection",
                "payment_status": "awaiting_payment",
                "recipient": "447000000001",
                "thread_id": "thread-1",
                "product_name": "Chilli Chicken",
                "price": 9.95,
                "quantity": 1,
            }
        ]
    )

    assert summary == {
        "order_id": "ORD-1",
        "order_type": "Paid Collection",
        "payment_status": "awaiting_payment",
        "recipient": "447000000001",
        "thread_id": "thread-1",
        "items": [{"product_name": "Chilli Chicken", "price": 9.95, "quantity": 1}],
        "currency": "GBP",
    }
