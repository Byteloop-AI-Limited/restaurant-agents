"""
Unit tests for services.order_service
    . Loads order_service with stubbed config (client_ordelo and logger)
    . Patches httpx.AsyncClient to avoid network requests
    . Verifies coordinate resolution from explicit values, rest_ref lookup, and error branches
    . Verifies get_min_order_value happy path, parsing, and HTTP-error fallback
  Functions/Classes:
    . _module
    . FakeResponse
    . FakeAsyncClient
    . FakeFactory
    . test_resolve_coords_uses_explicit_values
    . test_resolve_coords_requires_both_lat_and_lon
    . test_resolve_coords_uses_rest_ref_lookup
    . test_resolve_coords_raises_when_rest_ref_missing
    . test_resolve_coords_raises_when_no_inputs
    . test_get_min_order_value_returns_value
    . test_get_min_order_value_returns_none_on_http_error
"""


import httpx
import pytest

from tests._stubs.config_stub import (
    FakeSupabaseClient,
)
from tests._stubs.loader import load_module


@pytest.fixture
def order_service_module(monkeypatch):
    return load_module(
        "test_order_service_module",
        "restaurant_agent_core.services/order_service.py",
        monkeypatch,
    )


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, raise_for_status_exc=None):
        self._json = json_data or {}
        self.status_code = status_code
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


def _patch_httpx(monkeypatch, module, response):
    capture = []

    def factory(*args, **kwargs):
        return FakeAsyncClient(response, capture)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)
    return capture


def test_resolve_coords_uses_explicit_values(order_service_module):
    lat, lon = order_service_module._resolve_restaurant_coordinates(51.0, -0.1, None)

    assert (lat, lon) == (51.0, -0.1)


def test_resolve_coords_requires_both_lat_and_lon(order_service_module):
    with pytest.raises(ValueError):
        order_service_module._resolve_restaurant_coordinates(51.0, None, None)


def test_resolve_coords_uses_rest_ref_lookup(order_service_module, monkeypatch):
    fake_client = FakeSupabaseClient(
        table_data={"restaurant_master": [{"lat": 51.06, "lon": -1.79}]}
    )
    monkeypatch.setattr(order_service_module, "client_ordelo", fake_client)

    lat, lon = order_service_module._resolve_restaurant_coordinates(None, None, "elas")

    assert (lat, lon) == (51.06, -1.79)


def test_resolve_coords_raises_when_rest_ref_missing(order_service_module, monkeypatch):
    fake_client = FakeSupabaseClient(table_data={"restaurant_master": []})
    monkeypatch.setattr(order_service_module, "client_ordelo", fake_client)

    with pytest.raises(ValueError):
        order_service_module._resolve_restaurant_coordinates(None, None, "unknown")


def test_resolve_coords_raises_when_no_inputs(order_service_module):
    with pytest.raises(ValueError):
        order_service_module._resolve_restaurant_coordinates(None, None, None)


@pytest.mark.asyncio
async def test_get_min_order_value_returns_value(order_service_module, monkeypatch):
    fake_client = FakeSupabaseClient(
        table_data={"ordelo_config": [{"config_value": "https://ordelo.test"}]}
    )
    monkeypatch.setattr(order_service_module, "client_ordelo", fake_client)

    capture = _patch_httpx(
        monkeypatch,
        order_service_module,
        FakeResponse(json_data={"min_order_value": 12.5}),
    )

    result = await order_service_module.get_min_order_value(51.0, -0.1, "elas")

    assert result == 12.5
    url, params = capture[0]
    assert url == "https://ordelo.test/order-hooks/get-min-order-value"
    assert params == {
        "customer_latitude": 51.0,
        "customer_longitude": -0.1,
        "rest_ref": "elas",
    }


@pytest.mark.asyncio
async def test_get_min_order_value_returns_none_on_http_error(
    order_service_module, monkeypatch
):
    fake_client = FakeSupabaseClient(
        table_data={"ordelo_config": [{"config_value": "https://ordelo.test"}]}
    )
    monkeypatch.setattr(order_service_module, "client_ordelo", fake_client)

    response = FakeResponse(
        raise_for_status_exc=httpx.HTTPError("boom")
    )
    _patch_httpx(monkeypatch, order_service_module, response)

    result = await order_service_module.get_min_order_value(51.0, -0.1, "elas")

    assert result is None


@pytest.mark.asyncio
async def test_get_min_order_value_returns_none_on_unexpected_error(
    order_service_module, monkeypatch
):
    # config lookup itself raises → unexpected branch returns None
    class Broken:
        def table(self, *a, **k):
            raise RuntimeError("config unreachable")

    monkeypatch.setattr(order_service_module, "client_ordelo", Broken())

    result = await order_service_module.get_min_order_value(51.0, -0.1, "elas")

    assert result is None
