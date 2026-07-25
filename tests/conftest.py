"""
Shared pytest fixtures for deterministic unit tests
    . Provides fake async database pool fixtures without live Postgres access
    . Provides reusable sample WhatsApp-style order data and SKU mappings
    . Supports tests that exercise order-management code without external services
  Functions/Classes:
    . ProductStub
    . OrderStub
    . sample_order_data
    . mock_sku_product_map
    . sample_wa_order
    . fake_pool
"""

from dataclasses import dataclass

import pytest

from tests._stubs.pool_stub import FakeAsyncPool


@dataclass
class ProductStub:
    sku: str
    quantity: int
    price: float
    currency: str = "GBP"
    product_name: str | None = None
    modifications: list[str] | None = None


@dataclass
class OrderStub:
    catalog_id: str
    products: tuple[ProductStub, ...]
    text: str = ""

    @property
    def total_price(self) -> float:
        return round(sum(product.price * product.quantity for product in self.products), 2)


@pytest.fixture
def fake_pool():
    return FakeAsyncPool()

@pytest.fixture
def sample_order_data():
    """Fixture to provide sample order data for tests."""
    return {
        'catalog_id': '875083621367251',
        'products': [
            {'sku': 'chilli_chicken', 'quantity': 1, 'price': 9.95, 'currency': 'GBP'},
            {'sku': 'aloo_gobi', 'quantity': 2, 'price': 9.95, 'currency': 'GBP'},
        ],
        'text': ''
    }

@pytest.fixture
def mock_sku_product_map():
    """Fixture to provide mock SKU to product name mapping."""
    return {
        'chilli_chicken': 'Chilli Chicken',
        'aloo_gobi': 'Aloo Gobi',
        'mango_lassi': 'Mango Lassi',
        'apple_and_mango_smoothie': 'Apple and Mango Smoothie'
    }


@pytest.fixture
def sample_wa_order():
    return OrderStub(
        catalog_id="875083621367251",
        products=(
            ProductStub(
                sku="chilli_chicken",
                quantity=1,
                price=9.95,
                product_name="Chilli Chicken",
            ),
            ProductStub(
                sku="aloo_gobi",
                quantity=2,
                price=9.95,
                product_name="Aloo Gobi",
            ),
        ),
        text="",
    )
