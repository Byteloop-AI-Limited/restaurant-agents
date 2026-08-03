from types import SimpleNamespace

import pytest

from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)


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


class FakeDatabaseClient:
    def __init__(self, config):
        self.config = config
        self.config_reads = []

    def table(self, table_name):
        assert table_name == "ordelo_config"
        return FakeConfigQuery(self)


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
