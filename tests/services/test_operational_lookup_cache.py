from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)

UK_TZ = ZoneInfo("Europe/London")


class FakeConfigQuery:
    def __init__(self, client):
        self.client = client
        self.config_key = None

    def select(self, _fields):
        return self

    def eq(self, _field, value):
        self.config_key = value
        return self

    def limit(self, _count):
        return self

    def execute(self):
        self.client.config_reads.append(self.config_key)
        if self.config_key not in self.client.config:
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=[{"config_value": self.client.config[self.config_key]}])


class FakeRestaurantMasterQuery:
    def __init__(self, client):
        self.client = client

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def execute(self):
        self.client.restaurant_master_reads += 1
        return SimpleNamespace(data=[self.client.restaurant_master_row])


def _restaurant_master_row(*, service_hours_json):
    return {
        "rest_ref": "SFCS",
        "rest_name": "Test Restaurant",
        "house_number": "1",
        "street_name": "High Street",
        "city": "Salisbury",
        "postcode": "SP1 1AA",
        "lat": 51.0,
        "lon": -1.8,
        "dt": "2026-01-01",
        "dtts": "2026-01-01T00:00:00+00:00",
        "service_hours_json": service_hours_json,
    }


class FakeDatabaseClient:
    def __init__(self, config, *, restaurant_master_row=None):
        self.config = config
        self.config_reads = []
        self.restaurant_master_row = restaurant_master_row
        self.restaurant_master_reads = 0

    def table(self, table_name):
        if table_name == "ordelo_config":
            return FakeConfigQuery(self)
        if table_name == "restaurant_master":
            return FakeRestaurantMasterQuery(self)
        raise AssertionError(f"Unexpected table: {table_name}")


def test_app_url_is_cached_until_its_ttl_expires():
    now = [100.0]
    database_client = FakeDatabaseClient({"ORDELO_APP_URL": "https://one.test"})
    cache = OperationalLookupCache(
        rest_ref="SFCS",
        database_client=database_client,
        app_url_ttl_seconds=10,
        clock=lambda: now[0],
    )

    assert cache.get_app_url("ordelo") == "https://one.test"
    database_client.config["ORDELO_APP_URL"] = "https://two.test"
    assert cache.get_app_url("ORDELO") == "https://one.test"
    now[0] += 10
    assert cache.get_app_url("ORDELO") == "https://two.test"
    assert database_client.config_reads == ["ORDELO_APP_URL", "ORDELO_APP_URL"]


def test_missing_config_is_not_cached():
    database_client = FakeDatabaseClient({})
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)

    with pytest.raises(ValueError, match="ORDELO_APP_URL"):
        cache.get_app_url("ORDELO")
    database_client.config["ORDELO_APP_URL"] = "https://ordelo.test"

    assert cache.get_app_url("ORDELO") == "https://ordelo.test"
    assert database_client.config_reads == ["ORDELO_APP_URL", "ORDELO_APP_URL"]


def test_overwatch_recipients_are_normalized_and_fail_closed():
    database_client = FakeDatabaseClient(
        {"overwatch_list": " +447000000001, 447000000002 , "}
    )
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)

    assert cache.is_overwatch_recipient("+447000000001")
    assert cache.is_overwatch_recipient("447000000002")
    assert not cache.is_overwatch_recipient("447000000003")
    assert database_client.config_reads == ["overwatch_list"]

    failing_cache = OperationalLookupCache(
        rest_ref="SFCS", database_client=FakeDatabaseClient({})
    )
    assert not failing_cache.is_overwatch_recipient("447000000001")


def test_reset_respects_scope_and_optional_app_reference():
    database_client = FakeDatabaseClient(
        {
            "ORDELO_APP_URL": "https://ordelo.test",
            "RESTAURANT_MENU_APP_URL": "https://menu.test",
            "overwatch_list": "447000000001",
        }
    )
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)
    cache.get_app_url("ORDELO")
    cache.get_app_url("RESTAURANT_MENU")
    cache.get_overwatch_recipients()

    assert cache.reset(scope="operational_config", app_ref="ORDELO") == {
        "operational_config": 1,
        "restaurant_master": 0,
        "overwatch": 0,
    }
    assert cache.reset(scope="all") == {
        "operational_config": 1,
        "restaurant_master": 0,
        "overwatch": 1,
    }


def test_accepts_new_order_and_is_open_bypass_for_overwatch_when_closed():
    """Overwatch exercises the complete flow as though inside service hours."""
    closed_row = _restaurant_master_row(service_hours_json={})
    database_client = FakeDatabaseClient(
        {"overwatch_list": "447000000001"},
        restaurant_master_row=closed_row,
    )
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)
    at = datetime(2026, 1, 5, 12, 0, tzinfo=UK_TZ)  # closed every day of the week

    assert cache.accepts_new_order("delivery", "447000000001", at) is True
    assert cache.accepts_new_order("takeaway", "447000000001", at) is True
    assert cache.is_open("447000000001", at) is True

    assert cache.accepts_new_order("delivery", "447000000002", at) is False
    assert cache.accepts_new_order("takeaway", "447000000002", at) is False
    assert cache.is_open("447000000002", at) is False
    assert cache.accepts_new_order("delivery", None, at) is False
    assert cache.is_open(None, at) is False


def test_accepts_new_order_and_is_open_delegate_to_restaurant_master_when_open():
    open_row = _restaurant_master_row(service_hours_json={"mon": [["09:00", "23:00"]]})
    database_client = FakeDatabaseClient({}, restaurant_master_row=open_row)
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)
    at = datetime(2026, 1, 5, 12, 0, tzinfo=UK_TZ)  # Monday, inside hours

    assert cache.accepts_new_order("delivery", "447000000009", at) is True
    assert cache.accepts_new_order("takeaway", "447000000009", at) is True
    assert cache.is_open("447000000009", at) is True

    closed_at = datetime(2026, 1, 6, 12, 0, tzinfo=UK_TZ)  # Tuesday, no hours configured
    assert cache.accepts_new_order("delivery", "447000000009", closed_at) is False
    assert cache.is_open("447000000009", closed_at) is False


def test_accepts_new_order_rejects_unknown_order_type():
    open_row = _restaurant_master_row(service_hours_json={"mon": [["09:00", "23:00"]]})
    database_client = FakeDatabaseClient({}, restaurant_master_row=open_row)
    cache = OperationalLookupCache(rest_ref="SFCS", database_client=database_client)
    at = datetime(2026, 1, 5, 12, 0, tzinfo=UK_TZ)

    with pytest.raises(ValueError, match="Unknown order type"):
        cache.accepts_new_order("dine_in", "447000000009", at)
