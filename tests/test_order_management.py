"""
Unit tests for order-management database orchestration using fake async pools
    . Replaces live Postgres-dependent tests with deterministic fake cursor tests
    . Verifies SQL-backed helpers through recorded fake-pool interactions
    . Covers payment-link HTTP success and error paths without external requests
  Functions/Classes:
    . test_order_creation
    . test_create_order_items
    . test_process_order_into_db
    . test_create_order_summary
    . test_get_stripe_payment_link
    . test_get_stripe_payment_link_returns_none_on_http_error
"""

from types import SimpleNamespace

import httpx
import pytest
from pywa.types import Product

from tests._stubs.loader import load_module
from tests._stubs.pool_stub import FakeAsyncPool


@pytest.fixture
def order_db_ops(monkeypatch):
    return load_module(
        "test_order_management_order_db_ops_module",
        "restaurant_agent_runtime.services/order_management/order_db_ops.py",
        monkeypatch,
    )


@pytest.mark.asyncio
async def test_order_creation(order_db_ops):
    order = order_db_ops.Order(
        catalog_id="875083621367251",
        products=(
            Product(sku="chilli_chicken", quantity=1, price=9.95, currency="GBP"),
            Product(sku="aloo_gobi", quantity=2, price=9.95, currency="GBP"),
        ),
        text="",
    )
    assert order.catalog_id == "875083621367251"
    assert len(order.products) == 2
    assert order.products[0].sku == "chilli_chicken"


@pytest.mark.asyncio
async def test_create_order_items(order_db_ops, mock_sku_product_map):
    order = order_db_ops.Order(
        catalog_id="875083621367251",
        products=(
            Product(sku="mango_lassi", quantity=1, price=4.5, currency="GBP"),
        ),
        text="",
    )

    order_items = await order_db_ops.create_order_items_from_order(
        order,
        order_id="test_123",
        sku_nam_map=mock_sku_product_map,
    )
    assert len(order_items) == 1
    assert order_items[0].product_name == "Mango Lassi"


@pytest.mark.asyncio
async def test_process_order_into_db(order_db_ops):
    pool = FakeAsyncPool(fetchone_result={"get_next_daily_seq": 3})
    order = order_db_ops.Order(
        catalog_id="875083621367251",
        products=(
            Product(sku="chilli_chicken", quantity=1, price=9.95, currency="GBP"),
        ),
        text="",
    )

    order_id = await order_db_ops.process_order_into_db(
        pool,
        recipient="447424334783",
        thread_id="test_conv_123",
        wa_order=order,
    )

    assert order_id is not False
    assert pool.cursor_obj.executed
    assert pool.cursor_obj.executemany_calls


@pytest.mark.asyncio
async def test_create_order_summary(order_db_ops):
    pool = FakeAsyncPool(
        fetchall_result=[
            {
                "product_name": "Chilli Chicken",
                "price": 9.95,
                "quantity": 1,
                "order_id": "ORD-1",
                "order_type": "Paid Collection",
                "payment_status": "awaiting_payment",
                "recipient": "447424334783",
                "thread_id": "test_conv_124",
            }
        ]
    )

    summary = await order_db_ops.create_order_summary_from_db(pool, order_id="ORD-1")
    assert summary["order_id"] == "ORD-1"
    assert summary["items"] == [
        {"product_name": "Chilli Chicken", "price": 9.95, "quantity": 1}
    ]
    assert summary["currency"] == "GBP"


@pytest.mark.asyncio
async def test_get_stripe_payment_link(monkeypatch, order_db_ops):
    pool = FakeAsyncPool(
        fetchall_result=[
            {
                "product_name": "Chilli Chicken",
                "price": 9.95,
                "quantity": 1,
                "order_id": "ORD-1",
                "order_type": "Paid Collection",
                "payment_status": "awaiting_payment",
                "recipient": "447424334783",
                "thread_id": "test_conv_125",
            }
        ]
    )

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"url": "https://pay.test/ORD-1"},
            )

    monkeypatch.setattr(order_db_ops.httpx, "AsyncClient", FakeAsyncClient)

    payment_link = await order_db_ops.get_stripe_payment_link(pool, order_id="ORD-1")
    assert payment_link == "https://pay.test/ORD-1"


@pytest.mark.asyncio
async def test_get_stripe_payment_link_returns_none_on_http_error(monkeypatch, order_db_ops):
    pool = FakeAsyncPool(
        fetchall_result=[
            {
                "product_name": "Chilli Chicken",
                "price": 9.95,
                "quantity": 1,
                "order_id": "ORD-1",
                "order_type": "Paid Collection",
                "payment_status": "awaiting_payment",
                "recipient": "447424334783",
                "thread_id": "test_conv_125",
            }
        ]
    )

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            def raise_for_status():
                raise httpx.HTTPError("boom")

            return SimpleNamespace(raise_for_status=raise_for_status)

    monkeypatch.setattr(order_db_ops.httpx, "AsyncClient", FakeAsyncClient)

    payment_link = await order_db_ops.get_stripe_payment_link(pool, order_id="ORD-1")
    assert payment_link is None
