"""
Unit tests for Ordelo service Pydantic datamodels
    . Loads CustomerMaster, CreateOrUpdateCustomerRequest, UpdateAddressRequest, UpdateCustRestMapRequest
    . Loads CustRestMap with consent-window logic
    . Stubs config.client_ordelo via FakeSupabaseClient
    . Asserts validators, lookup/upsert helpers and consent logic
  Functions/Classes:
    . test_customer_master_defaults_for_house_number_and_street
    . test_customer_master_from_cust_id_returns_instance
    . test_customer_master_from_cust_id_raises_when_missing
    . test_customer_master_upsert_requires_cust_id
    . test_customer_master_upsert_returns_instance
    . test_create_or_update_customer_request_minimal
    . test_update_address_request_requires_city_postcode_lat_lon
    . test_update_cust_rest_map_request_serialises_datetime
    . test_cust_rest_map_from_cust_id_and_rest_ref_returns_instance
    . test_cust_rest_map_from_cust_id_raises_when_missing
    . test_cust_rest_map_upsert_returns_instance
    . test_ask_for_marketing_consent_already_consented
    . test_ask_for_marketing_consent_never_asked
    . test_ask_for_marketing_consent_within_window
    . test_ask_for_marketing_consent_outside_window
    . test_ask_for_marketing_consent_negative_days_raises
"""

import datetime
from datetime import timezone

import pytest

from tests._stubs.config_stub import (
    FakeSupabaseClient,
)


@pytest.fixture(autouse=True)
def _stub_config(monkeypatch):
    """Inject a fake `config` module before importing the datamodels."""
    import sys
    from tests._stubs.config_stub import build_config_stub

    config_stub = build_config_stub()
    monkeypatch.setitem(sys.modules, "restaurant_agent_runtime.config", config_stub)
    yield config_stub


@pytest.fixture
def customer_module():
    # Import inside fixture to honour monkeypatched config
    import importlib
    import restaurant_agent_runtime.services.ordelo_service.datamodels.customer_master_pymodel as module
    importlib.reload(module)
    return module


@pytest.fixture
def cust_rest_map_module():
    import importlib
    import restaurant_agent_runtime.services.ordelo_service.datamodels.cust_rest_map_pymodel as module
    importlib.reload(module)
    return module


def _patch_client_ordelo(monkeypatch, fake_client):
    import sys
    sys.modules["restaurant_agent_runtime.config"].client_ordelo = fake_client


def test_customer_master_defaults_for_house_number_and_street(customer_module):
    # The before validators coerce explicit Nones; absent fields keep their default (None)
    cm = customer_module.CustomerMaster(
        cust_id="447000000001", house_number=None, street_name=None
    )

    assert cm.house_number == "999"
    assert cm.street_name == ""
    assert cm.cust_name is None


def test_customer_master_from_cust_id_returns_instance(customer_module, monkeypatch):
    fake_client = FakeSupabaseClient(
        table_data={
            "customer_master": [{"cust_id": "447000000001", "cust_name": "Bas"}]
        }
    )
    _patch_client_ordelo(monkeypatch, fake_client)

    cm = customer_module.CustomerMaster.from_cust_id("447000000001")

    assert cm.cust_id == "447000000001"
    assert cm.cust_name == "Bas"


def test_customer_master_from_cust_id_raises_when_missing(customer_module, monkeypatch):
    fake_client = FakeSupabaseClient(table_data={"customer_master": []})
    _patch_client_ordelo(monkeypatch, fake_client)

    with pytest.raises(ValueError):
        customer_module.CustomerMaster.from_cust_id("missing")


def test_customer_master_upsert_requires_cust_id(customer_module, monkeypatch):
    fake_client = FakeSupabaseClient(table_data={"customer_master": []})
    _patch_client_ordelo(monkeypatch, fake_client)

    with pytest.raises(ValueError):
        customer_module.CustomerMaster.upsert(cust_name="Bas")


def test_customer_master_upsert_returns_instance(customer_module, monkeypatch):
    fake_client = FakeSupabaseClient(
        table_data={
            "customer_master": [{"cust_id": "447000000001", "cust_name": "Bas"}]
        }
    )
    _patch_client_ordelo(monkeypatch, fake_client)

    cm = customer_module.CustomerMaster.upsert(
        cust_id="447000000001", cust_name="Bas", ignored="x"
    )

    assert cm.cust_id == "447000000001"
    assert cm.cust_name == "Bas"
    # ensure upsert call was issued
    call_names = [c[0] for c in fake_client.queries[0].calls]
    assert "upsert" in call_names


def test_create_or_update_customer_request_minimal(customer_module):
    req = customer_module.CreateOrUpdateCustomerRequest(
        cust_id="447000000001", rest_ref="ELAS"
    )

    payload = req.model_dump(exclude_none=True)
    assert payload == {"cust_id": "447000000001", "rest_ref": "ELAS"}


def test_update_address_request_requires_city_postcode_lat_lon(customer_module):
    with pytest.raises(Exception):
        customer_module.UpdateAddressRequest(
            cust_id="447000000001", rest_ref="ELAS"
        )

    req = customer_module.UpdateAddressRequest(
        cust_id="447000000001",
        rest_ref="ELAS",
        city="London",
        postcode="BR6 6DN",
        lat=51.0,
        lon=-0.1,
    )
    assert req.lat == 51.0


def test_update_cust_rest_map_request_serialises_datetime(customer_module):
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    req = customer_module.UpdateCustRestMapRequest(
        cust_id="447000000001",
        rest_ref="ELAS",
        has_consent=True,
        consent_dtts=now,
    )

    payload = req.model_dump(mode="json", exclude_none=True)
    assert payload["has_consent"] is True
    assert payload["consent_dtts"].startswith("2026-01-01")


def test_cust_rest_map_from_cust_id_and_rest_ref_returns_instance(
    cust_rest_map_module, monkeypatch
):
    fake_client = FakeSupabaseClient(
        table_data={
            "cust_rest_map": [
                {
                    "cust_id": "447000000001",
                    "rest_ref": "ELAS",
                    "has_consent": True,
                }
            ]
        }
    )
    _patch_client_ordelo(monkeypatch, fake_client)

    record = cust_rest_map_module.CustRestMap.from_cust_id_and_rest_ref(
        "447000000001", "elas"
    )

    assert record.has_consent is True
    # rest_ref normalised on query (eq call) — confirm by capturing eq calls
    eq_calls = [c for c in fake_client.queries[0].calls if c[0] == "eq"]
    assert any(call[1] == ("rest_ref", "ELAS") for call in eq_calls)


def test_cust_rest_map_from_cust_id_raises_when_missing(
    cust_rest_map_module, monkeypatch
):
    fake_client = FakeSupabaseClient(table_data={"cust_rest_map": []})
    _patch_client_ordelo(monkeypatch, fake_client)

    with pytest.raises(ValueError):
        cust_rest_map_module.CustRestMap.from_cust_id_and_rest_ref(
            "447000000001", "elas"
        )


def test_cust_rest_map_upsert_returns_instance(cust_rest_map_module, monkeypatch):
    fake_client = FakeSupabaseClient(
        table_data={
            "cust_rest_map": [
                {
                    "cust_id": "447000000001",
                    "rest_ref": "ELAS",
                    "has_consent": True,
                }
            ]
        }
    )
    _patch_client_ordelo(monkeypatch, fake_client)

    record = cust_rest_map_module.CustRestMap.upsert(
        cust_id="447000000001",
        rest_ref="elas",
        has_consent=True,
        consent_dtts=datetime.datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert record.has_consent is True
    call_names = [c[0] for c in fake_client.queries[0].calls]
    assert "upsert" in call_names


def test_ask_for_marketing_consent_already_consented(cust_rest_map_module):
    record = cust_rest_map_module.CustRestMap(
        cust_id="447000000001", rest_ref="ELAS", has_consent=True
    )
    assert record.ask_for_marketing_consent(30) is False


def test_ask_for_marketing_consent_never_asked(cust_rest_map_module):
    record = cust_rest_map_module.CustRestMap(
        cust_id="447000000001", rest_ref="ELAS", has_consent=False, consent_dtts=None
    )
    assert record.ask_for_marketing_consent(30) is True


def test_ask_for_marketing_consent_within_window(cust_rest_map_module):
    consent_dtts = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=1)
    record = cust_rest_map_module.CustRestMap(
        cust_id="447000000001",
        rest_ref="ELAS",
        has_consent=False,
        consent_dtts=consent_dtts,
    )
    assert record.ask_for_marketing_consent(30) is False


def test_ask_for_marketing_consent_outside_window(cust_rest_map_module):
    consent_dtts = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=60)
    record = cust_rest_map_module.CustRestMap(
        cust_id="447000000001",
        rest_ref="ELAS",
        has_consent=False,
        consent_dtts=consent_dtts,
    )
    assert record.ask_for_marketing_consent(30) is True


def test_ask_for_marketing_consent_negative_days_raises(cust_rest_map_module):
    record = cust_rest_map_module.CustRestMap(
        cust_id="447000000001", rest_ref="ELAS", has_consent=False
    )
    with pytest.raises(ValueError):
        record.ask_for_marketing_consent(-1)
