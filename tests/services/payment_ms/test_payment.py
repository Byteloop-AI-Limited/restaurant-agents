"""
Unit tests for payment microservice helpers
    . Loads payment helpers with stubbed config, FoodOrder, and Supabase clients
    . Mocks httpx AsyncClient to avoid network calls
    . Covers payment URI construction, intent generation, cancel/capture, and order summaries
  Functions/Classes:
    . FakeAsyncClientFactory
    . FakeResponse
    . payment_module
    . food_order
    . test_get_payment_uri
    . test_generate_payment_intent_posts_payload_and_returns_url
    . test_generate_payment_intent_returns_none_on_http_error
    . test_cancel_and_capture_payment_success_and_failure
    . test_generate_order_summary_for_payment_intent_adds_positive_fees
"""

from types import ModuleType, SimpleNamespace

import httpx
import pytest

from tests._stubs.config_stub import FakeSupabaseClient, build_config_stub
from tests._stubs.loader import load_module


class FakeResponse:
    def __init__(self, json_data=None, text="", error=None):
        self._json_data = json_data or {}
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self._json_data


class FakeAsyncClientFactory:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def __call__(self):
        factory = self

        class FakeAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json, headers):
                factory.posts.append({"url": url, "json": json, "headers": headers})
                return factory.response

        return FakeAsyncClient()


@pytest.fixture
def payment_module(monkeypatch):
    config_stub = build_config_stub()
    config_stub.client_ordelo = FakeSupabaseClient(
        table_data={
            "order_item": [{"product_name": "Curry", "quantity": 2, "price": 8.0}]
        }
    )

    food_order_module = ModuleType("restaurant_agent_runtime.services.order_management.food_order_pymodel")
    food_order_module.FoodOrder = object

    return load_module(
        "test_payment_module",
        "restaurant_agent_runtime.services/payment_ms/payment.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_runtime.services.order_management.food_order_pymodel": food_order_module,
        },
    )


@pytest.fixture
def food_order():
    async def gen_payload():
        return {"items": [{"product_name": "Curry", "quantity": 1, "price": 8.0}]}

    return SimpleNamespace(
        order_id="ORD-1",
        payment_uri="https://stripe.test/threads/thread-1/orders/ORD-1/payment-url",
        gen_payment_intent_payload=gen_payload,
        service_charge=1.0,
        delivery_fee=2.5,
        small_order_fee=0.0,
    )


def test_get_payment_uri(payment_module):
    assert payment_module.get_payment_uri("ORD-1", "thread-1") == (
        "https://stripe.test/threads/thread-1/orders/ORD-1/payment-url"
    )


@pytest.mark.asyncio
async def test_generate_payment_intent_posts_payload_and_returns_url(monkeypatch, payment_module, food_order):
    factory = FakeAsyncClientFactory(FakeResponse({"url": "https://pay.test/ORD-1"}))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", factory)

    url = await payment_module.generate_payment_intent(food_order)

    assert url == "https://pay.test/ORD-1"
    assert factory.posts == [
        {
            "url": food_order.payment_uri,
            "json": {"items": [{"product_name": "Curry", "quantity": 1, "price": 8.0}]},
            "headers": {"Authorization": "Bearer test"},
        }
    ]


@pytest.mark.asyncio
async def test_generate_payment_intent_returns_none_on_http_error(monkeypatch, payment_module, food_order):
    factory = FakeAsyncClientFactory(FakeResponse(error=httpx.HTTPError("boom")))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", factory)

    assert await payment_module.generate_payment_intent(food_order) is None


@pytest.mark.asyncio
async def test_cancel_and_capture_payment_success_and_failure(monkeypatch, payment_module):
    success_factory = FakeAsyncClientFactory(FakeResponse(text=""))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", success_factory)

    assert await payment_module.cancel_payment("ORD-1", "thread-1") is True
    assert success_factory.posts[0]["json"] == {"action": "delivery", "payment_mode": "cancel"}
    assert await payment_module.capture_payment("ORD-1", "thread-1") is True
    assert success_factory.posts[1]["json"]["payment_mode"] == "capture"

    error_factory = FakeAsyncClientFactory(FakeResponse(error=httpx.HTTPError("boom")))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", error_factory)
    assert await payment_module.cancel_payment("ORD-1", "thread-1") is False
    assert await payment_module.capture_payment("ORD-1", "thread-1") is False


@pytest.mark.asyncio
async def test_generate_order_summary_for_payment_intent_adds_positive_fees(payment_module, food_order):
    summary = await payment_module.generate_order_summary_for_payment_intent(food_order)

    assert summary == {
        "items": [
            {"product_name": "Curry", "quantity": 2, "price": 8.0},
            {"product_name": "Service Charge", "quantity": 1, "price": 1.0},
            {"product_name": "Delivery Fee", "quantity": 1, "price": 2.5},
        ]
    }
