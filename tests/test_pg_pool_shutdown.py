"""
Tests for PgSetting.close_pool
    . Closes and clears the async pool when it is open
    . Is a harmless no-op when no pool exists
    . Skips closing an already-closed pool but still clears the reference
    . Loads config/pg_setting.py in isolation with a stubbed utils.aws_setting so
      the module-level AWS Secrets Manager fetch and full config package import do
      not run
"""

from unittest.mock import AsyncMock

from tests._stubs.loader import load_module

PG_FAKE_SECRET = {
    "sbase_ordelo_db_uri": "postgresql://u:p@localhost:5432/db",
    "sbase_ordelo_vec_db_uri": "postgresql://u:p@localhost:5432/db",
    "sbase_ordelo_rest_url": "https://example.supabase.co",
    "sbase_ordelo_rest_key": "rest-key",
    "sbase_ordelo_service_key": "service-key",
}


def _load_pg_module(monkeypatch):
    return load_module(
        "pg_setting_under_test",
        "restaurant_agent_runtime.config/pg_setting.py",
        monkeypatch,
    )


async def test_close_pool_closes_open_pool(monkeypatch):
    pg_mod = _load_pg_module(monkeypatch)
    settings = pg_mod.PgSetting(**PG_FAKE_SECRET)

    fake_pool = AsyncMock()
    fake_pool.closed = False
    settings._async_pool = fake_pool

    await settings.close_pool()

    fake_pool.close.assert_awaited_once()
    assert settings._async_pool is None


async def test_close_pool_noop_when_no_pool(monkeypatch):
    pg_mod = _load_pg_module(monkeypatch)
    settings = pg_mod.PgSetting(**PG_FAKE_SECRET)
    settings._async_pool = None

    await settings.close_pool()  # must not raise

    assert settings._async_pool is None


async def test_close_pool_skips_already_closed_pool(monkeypatch):
    pg_mod = _load_pg_module(monkeypatch)
    settings = pg_mod.PgSetting(**PG_FAKE_SECRET)

    fake_pool = AsyncMock()
    fake_pool.closed = True
    settings._async_pool = fake_pool

    await settings.close_pool()

    fake_pool.close.assert_not_awaited()
    assert settings._async_pool is None
