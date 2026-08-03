"""Contract tests for runtime-bound payment cancellation."""

from types import SimpleNamespace

import httpx
import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeResponse:
    def __init__(self, *, text="", error=None):
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


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
    return load_module(
        "test_payment_module",
        "restaurant_agent_runtime.services/payment_ms/payment.py",
        monkeypatch,
        {"config": build_config_stub()},
    )


@pytest.fixture
def payment_settings():
    return SimpleNamespace(
        headers={"Authorization": "Bearer test"},
        generate_payment_intent_url=lambda order_id, thread_id: (
            f"https://stripe.test/threads/{thread_id}/orders/{order_id}/payment-url"
        ),
    )


def test_get_payment_uri_uses_injected_settings(payment_module, payment_settings):
    assert payment_module.get_payment_uri(
        "ORD-1",
        "thread-1",
        payment_settings=payment_settings,
    ) == "https://stripe.test/threads/thread-1/orders/ORD-1/payment-url"


@pytest.mark.asyncio
async def test_cancel_payment_posts_contract(
    monkeypatch,
    payment_module,
    payment_settings,
):
    factory = FakeAsyncClientFactory(FakeResponse(text=""))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", factory)

    assert await payment_module.cancel_payment(
        "ORD-1",
        "thread-1",
        payment_settings=payment_settings,
    ) is True
    assert factory.posts == [
        {
            "url": "https://stripe.test/threads/thread-1/orders/ORD-1/payment-url",
            "json": {"action": "delivery", "payment_mode": "cancel"},
            "headers": {"Authorization": "Bearer test"},
        }
    ]


@pytest.mark.asyncio
async def test_cancel_payment_returns_false_on_http_error(
    monkeypatch,
    payment_module,
    payment_settings,
):
    factory = FakeAsyncClientFactory(FakeResponse(error=httpx.HTTPError("boom")))
    monkeypatch.setattr(payment_module.httpx, "AsyncClient", factory)

    assert await payment_module.cancel_payment(
        "ORD-1",
        "thread-1",
        payment_settings=payment_settings,
    ) is False
