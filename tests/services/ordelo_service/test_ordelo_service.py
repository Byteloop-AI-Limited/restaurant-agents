"""
Unit tests for OrdeloService HTTP client
    . Stubs httpx.AsyncClient to capture POST URL and JSON payload
    . Stubs config.params.get_restaurant_base_url_async for base URL
    . Verifies happy path, HTTP error returns None, and dispatch URLs
  Functions/Classes:
    . FakeResponse
    . FakeAsyncClient
    . _patch_httpx
    . _stub_get_base_url
    . test_create_or_update_customer_posts_payload
    . test_create_or_update_customer_returns_none_on_http_error
    . test_update_address_posts_payload
    . test_update_cust_rest_map_posts_payload
    . test_get_or_create_customer_master_new_customer
    . test_get_or_create_customer_master_existing_customer_no_name
    . test_get_or_create_customer_master_existing_customer_with_name
"""

import sys
from types import ModuleType, SimpleNamespace

import httpx
import pytest


@pytest.fixture(autouse=True)
def _stub_config(monkeypatch):
    from tests._stubs.config_stub import build_config_stub

    config_stub = build_config_stub()
    monkeypatch.setitem(sys.modules, "config", config_stub)

    params_stub = ModuleType("restaurant_agent_runtime.config.params")

    async def get_restaurant_base_url_async(key, *, database_client):
        return "https://ordelo.test"

    params_stub.get_restaurant_base_url_async = get_restaurant_base_url_async
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.config.params", params_stub)
    yield config_stub


@pytest.fixture
def ordelo_module():
    import importlib
    import restaurant_agent_runtime.services.ordelo_service.ordelo_service as module
    importlib.reload(module)
    return module


class FakeResponse:
    def __init__(self, json_data=None, raise_exc=None):
        self._json = json_data or {}
        self._raise = raise_exc

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

    async def post(self, url, json=None):
        self._capture.append((url, json))
        return self._response


def _patch_httpx(monkeypatch, module, response):
    capture = []

    def factory(*args, **kwargs):
        return FakeAsyncClient(response, capture)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)
    return capture


def _service(module):
    return module.OrdeloService(
        rest_ref="ELAS",
        database_client=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_create_or_update_customer_posts_payload(ordelo_module, monkeypatch):
    capture = _patch_httpx(
        monkeypatch,
        ordelo_module,
        FakeResponse(json_data={"cust_id": "447000000001"}),
    )
    svc = _service(ordelo_module)
    req = ordelo_module.CreateOrUpdateCustomerRequest(
        cust_id="447000000001", rest_ref="ELAS", cust_name="Bas"
    )

    result = await svc.create_or_update_customer(req)

    assert result == {"cust_id": "447000000001"}
    url, payload = capture[0]
    assert url == "https://ordelo.test/customer-hooks/create-or-update-customer"
    assert payload["cust_id"] == "447000000001"
    assert payload["cust_name"] == "Bas"
    assert "cust_email" not in payload  # exclude_none


@pytest.mark.asyncio
async def test_create_or_update_customer_returns_none_on_http_error(
    ordelo_module, monkeypatch
):
    _patch_httpx(
        monkeypatch,
        ordelo_module,
        FakeResponse(raise_exc=httpx.HTTPError("boom")),
    )
    svc = _service(ordelo_module)
    req = ordelo_module.CreateOrUpdateCustomerRequest(
        cust_id="447000000001", rest_ref="ELAS"
    )

    result = await svc.create_or_update_customer(req)
    assert result is None


@pytest.mark.asyncio
async def test_update_address_posts_payload(ordelo_module, monkeypatch):
    capture = _patch_httpx(monkeypatch, ordelo_module, FakeResponse(json_data={"ok": True}))
    svc = _service(ordelo_module)
    req = ordelo_module.UpdateAddressRequest(
        cust_id="447000000001",
        rest_ref="ELAS",
        city="London",
        postcode="BR6 6DN",
        lat=51.0,
        lon=-0.1,
    )

    await svc.update_address(req)

    url, payload = capture[0]
    assert url.endswith("/customer-hooks/update-address")
    assert payload["postcode"] == "BR6 6DN"


@pytest.mark.asyncio
async def test_update_cust_rest_map_posts_payload(ordelo_module, monkeypatch):
    capture = _patch_httpx(monkeypatch, ordelo_module, FakeResponse(json_data={"ok": True}))
    svc = _service(ordelo_module)
    req = ordelo_module.UpdateCustRestMapRequest(
        cust_id="447000000001", rest_ref="ELAS", has_consent=True
    )

    await svc.update_cust_rest_map(req)

    url, payload = capture[0]
    assert url.endswith("/customer-hooks/update-cust-rest-map")
    assert payload["has_consent"] is True


@pytest.mark.asyncio
async def test_get_or_create_customer_master_new_customer(ordelo_module, monkeypatch):
    # CustomerMaster.from_cust_id raises ValueError → new path
    def raise_value_error(*args, **kwargs):
        raise ValueError("missing")

    monkeypatch.setattr(
        ordelo_module.CustomerMaster, "from_cust_id", classmethod(raise_value_error)
    )

    async def fake_create(self, request):
        return {"cust_id": request.cust_id, "cust_name": request.cust_name}

    monkeypatch.setattr(
        ordelo_module.OrdeloService, "create_or_update_customer", fake_create
    )

    svc = _service(ordelo_module)
    customer, ask = await svc.get_or_create_customer_master(
        "447000000001", wa_name="Bas"
    )

    assert customer.cust_id == "447000000001"
    assert customer.cust_name == "Bas"
    assert ask is True


@pytest.mark.asyncio
async def test_get_or_create_customer_master_existing_customer_no_name(
    ordelo_module, monkeypatch
):
    existing = ordelo_module.CustomerMaster(cust_id="447000000001", cust_name="Bas")

    monkeypatch.setattr(
        ordelo_module.CustomerMaster,
        "from_cust_id",
        classmethod(lambda cls, cust_id, **kwargs: existing),
    )

    # Stub consent class to return ask=False for already-consented
    def fake_lookup(cls, cust_id, rest_ref, **kwargs):
        return SimpleNamespace(
            ask_for_marketing_consent=lambda days=30: False
        )

    monkeypatch.setattr(
        ordelo_module.CustRestMap,
        "from_cust_id_and_rest_ref",
        classmethod(fake_lookup),
    )

    svc = _service(ordelo_module)
    customer, ask = await svc.get_or_create_customer_master("447000000001")

    assert customer is existing
    assert ask is False


@pytest.mark.asyncio
async def test_get_or_create_customer_master_existing_with_name_consent_missing(
    ordelo_module, monkeypatch
):
    existing = ordelo_module.CustomerMaster(cust_id="447000000001", cust_name="Bas")
    monkeypatch.setattr(
        ordelo_module.CustomerMaster,
        "from_cust_id",
        classmethod(lambda cls, cust_id, **kwargs: existing),
    )

    async def fake_create(self, request):
        return {"cust_id": request.cust_id, "cust_name": request.cust_name}

    monkeypatch.setattr(
        ordelo_module.OrdeloService, "create_or_update_customer", fake_create
    )

    def raise_value_error(cls, cust_id, rest_ref, **kwargs):
        raise ValueError("no consent")

    monkeypatch.setattr(
        ordelo_module.CustRestMap,
        "from_cust_id_and_rest_ref",
        classmethod(raise_value_error),
    )

    svc = _service(ordelo_module)
    customer, ask = await svc.get_or_create_customer_master(
        "447000000001", wa_name="Other"
    )

    assert customer.cust_name == "Other"
    assert ask is True
