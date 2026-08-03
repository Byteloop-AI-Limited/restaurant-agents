"""Tests for runtime-bound minimum-order lookup."""

import httpx
import pytest

from restaurant_agent_runtime.services import order_service


class FakeOperationalLookups:
    def __init__(self, url: str | None = "https://ordelo.test"):
        self.url = url
        self.calls = 0

    def get_app_url(self, app_ref: str) -> str:
        assert app_ref == "ORDELO"
        self.calls += 1
        if self.url is None:
            raise ValueError("ORDELO_APP_URL is not configured")
        return self.url


class FakeResponse:
    def __init__(self, json_data=None, raise_for_status_exc=None):
        self._json = json_data or {}
        self._raise = raise_for_status_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._json


class FakeAsyncClient:
    def __init__(self, response, capture):
        self._response = response
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self._capture.append((url, params))
        return self._response


def _patch_httpx(monkeypatch, response):
    capture = []
    monkeypatch.setattr(
        order_service.httpx,
        "AsyncClient",
        lambda: FakeAsyncClient(response, capture),
    )
    return capture


@pytest.mark.asyncio
async def test_get_min_order_value_uses_runtime_operational_lookup(monkeypatch):
    operational_lookups = FakeOperationalLookups()
    capture = _patch_httpx(
        monkeypatch,
        FakeResponse(json_data={"min_order_value": 12.5}),
    )

    result = await order_service.get_min_order_value(
        51.0,
        -0.1,
        "SFCS",
        operational_lookups=operational_lookups,
    )

    assert result == 12.5
    assert capture == [
        (
            "https://ordelo.test/order-hooks/get-min-order-value",
            {
                "customer_latitude": 51.0,
                "customer_longitude": -0.1,
                "rest_ref": "SFCS",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_min_order_value_returns_none_on_http_error(monkeypatch):
    _patch_httpx(
        monkeypatch,
        FakeResponse(raise_for_status_exc=httpx.HTTPError("boom")),
    )

    assert await order_service.get_min_order_value(
        51.0,
        -0.1,
        "SFCS",
        operational_lookups=FakeOperationalLookups(),
    ) is None


@pytest.mark.asyncio
async def test_get_min_order_value_returns_none_without_config():
    assert await order_service.get_min_order_value(
        51.0,
        -0.1,
        "SFCS",
        operational_lookups=FakeOperationalLookups(url=None),
    ) is None
