"""
Unit tests for new order database operation pure helpers
    . Loads order_db_ops_new with stubbed config to avoid Supabase side effects
    . Covers order reference generation, total calculation, and order item conversion
    . Verifies validation and rounding behavior for customer order payloads
  Functions/Classes:
    . test_create_order_reference_is_deterministic
    . test_create_order_reference_rejects_invalid_recipient_tail
    . test_get_order_total_multiplies_quantity_and_rounds
    . test_create_order_items_from_order_preserves_fields
"""

import pytest

from tests._stubs.loader import load_module


@pytest.fixture
def order_db_ops_new(monkeypatch):
    return load_module(
        "test_order_db_ops_new_module",
        "restaurant_agent_runtime.services/order_management/order_db_ops_new.py",
        monkeypatch,
    )


def test_create_order_reference_is_deterministic(order_db_ops_new):
    first = order_db_ops_new.create_order_reference("447424331234", "2026-05-09")
    second = order_db_ops_new.create_order_reference("447424331234", "2026-05-09")
    assert first == second
    assert len(first) == 4
    assert first.isupper()


def test_create_order_reference_rejects_invalid_recipient_tail(order_db_ops_new):
    with pytest.raises(ValueError, match="4-digit"):
        order_db_ops_new.create_order_reference("abc", "2026-05-09")


def test_get_order_total_multiplies_quantity_and_rounds(order_db_ops_new, sample_wa_order):
    assert order_db_ops_new.get_order_total(sample_wa_order) == 29.85


@pytest.mark.asyncio
async def test_create_order_items_from_order_preserves_fields(order_db_ops_new, sample_wa_order):
    items = await order_db_ops_new.create_order_items_from_order(sample_wa_order, "ORD-1")

    assert len(items) == 2
    assert items[0].order_id == "ORD-1"
    assert items[0].sku == "chilli_chicken"
    assert items[0].quantity == 1
    assert items[0].product_name == "Chilli Chicken"
    assert items[0].modifications is None
