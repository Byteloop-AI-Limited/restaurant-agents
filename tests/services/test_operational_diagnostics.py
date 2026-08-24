from types import SimpleNamespace

import pytest

from restaurant_agent_runtime.services.operational_diagnostics import (
    application_url_details,
    reset_project_application_caches,
)
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
        value = self.client.config.get(self.config_key)
        data = [] if value is None else [{"config_value": value}]
        return SimpleNamespace(data=data)


class FakeDatabaseClient:
    def __init__(self, config):
        self.config = config

    def table(self, table_name):
        assert table_name == "ordelo_config"
        return FakeConfigQuery(self)


def _cache(config):
    return OperationalLookupCache(
        rest_ref="SFCS",
        database_client=FakeDatabaseClient(config),
    )


def test_application_url_details_use_cached_values_until_explicit_refresh():
    cache = _cache(
        {
            "ORDELO_APP_URL": "https://ordelo.one.test",
            "BNAT_APP_URL": "https://bnat.one.test",
            "SFCS_APP_URL": "https://sfcs.one.test",
            "ELAS_APP_URL": "https://elas.one.test",
        }
    )

    details, errors = application_url_details(cache)
    assert errors == {}
    assert details["BNAT_APP_URL"] == "https://bnat.one.test"

    cache._database_client.config["BNAT_APP_URL"] = "https://bnat.two.test"
    cached, _ = application_url_details(cache)
    refreshed, _ = application_url_details(cache, refresh=True)

    assert cached["BNAT_APP_URL"] == "https://bnat.one.test"
    assert refreshed["BNAT_APP_URL"] == "https://bnat.two.test"


@pytest.mark.asyncio
async def test_project_cache_reset_uses_fresh_urls_and_reports_each_app(monkeypatch):
    cache = _cache(
        {
            "ORDELO_APP_URL": "https://ordelo.test",
            "BNAT_APP_URL": "https://bnat.old.test",
            "SFCS_APP_URL": "https://sfcs.test",
            "ELAS_APP_URL": "https://elas.test",
        }
    )
    cache.get_app_url("BNAT")
    cache._database_client.config["BNAT_APP_URL"] = "https://bnat.new.test/"

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"scope": "all", "removed_entries": {"overwatch": 1}}

    class FakeClient:
        calls = []

        def __init__(self, *, follow_redirects, timeout):
            assert follow_redirects is False
            assert timeout == 10.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, params):
            self.calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(
        "restaurant_agent_runtime.services.operational_diagnostics.httpx.AsyncClient",
        FakeClient,
    )

    assert await reset_project_application_caches(cache) == {
        "BNAT": "reset",
        "ELAS": "reset",
        "ORDELO": "reset",
        "SFCS": "reset",
    }
    assert sorted(FakeClient.calls) == [
        ("https://bnat.new.test/internal/cache/reset", {"scope": "all"}),
        ("https://elas.test/internal/cache/reset", {"scope": "all"}),
        ("https://ordelo.test/internal/cache/reset", {"scope": "all"}),
        ("https://sfcs.test/internal/cache/reset", {"scope": "all"}),
    ]


@pytest.mark.asyncio
async def test_project_cache_reset_treats_zero_removed_entries_as_reset_not_failed(
    monkeypatch,
):
    """An empty process-local cache still means the reset ran; it must not be
    reported as "failed" just because nothing needed clearing."""
    cache = _cache(
        {
            "ORDELO_APP_URL": "https://ordelo.test",
            "BNAT_APP_URL": "https://bnat.test",
            "SFCS_APP_URL": "https://sfcs.test",
            "ELAS_APP_URL": "https://elas.test",
        }
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "scope": "all",
                "removed_entries": {
                    "operational_config": 0,
                    "restaurant_master": 0,
                    "overwatch": 0,
                },
            }

    class FakeClient:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, params):
            return FakeResponse()

    monkeypatch.setattr(
        "restaurant_agent_runtime.services.operational_diagnostics.httpx.AsyncClient",
        FakeClient,
    )

    outcomes = await reset_project_application_caches(cache)
    assert outcomes == {
        "BNAT": "reset",
        "ELAS": "reset",
        "ORDELO": "reset",
        "SFCS": "reset",
    }


@pytest.mark.asyncio
async def test_project_cache_reset_continues_after_unavailable_invalid_and_failed_targets(
    monkeypatch,
):
    cache = _cache(
        {
            "ORDELO_APP_URL": "https://ordelo.test",
            "BNAT_APP_URL": "https://bnat.test",
            "SFCS_APP_URL": "not-a-url",
        }
    )

    class FakeResponse:
        status_code = 503

        def json(self):
            raise AssertionError("A non-2xx response must not be parsed")

    class FakeClient:
        calls = []

        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, *, params):
            self.calls.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(
        "restaurant_agent_runtime.services.operational_diagnostics.httpx.AsyncClient",
        FakeClient,
    )

    assert await reset_project_application_caches(cache) == {
        "BNAT": "failed",
        "ELAS": "unavailable",
        "ORDELO": "failed",
        "SFCS": "invalid_url",
    }
    assert sorted(FakeClient.calls) == [
        ("https://bnat.test/internal/cache/reset", {"scope": "all"}),
        ("https://ordelo.test/internal/cache/reset", {"scope": "all"}),
    ]
