"""Tests for explicit, single-fetch Restaurant settings composition."""

from restaurant_agent_runtime.config import bundle as bundle_module
from restaurant_agent_runtime.runtime import RestaurantIdentity


def _secret_values():
    return {
        "project_settings_salt": "salt",
        "project_settings_rest_ref": "STALE",
        "sbase_ordelo_db_uri": "postgresql://u:p@localhost/db",
        "sbase_ordelo_vec_db_uri": "postgresql://u:p@localhost/vector",
        "sbase_ordelo_rest_url": "https://example.supabase.co",
        "sbase_ordelo_rest_key": "rest-key",
        "sbase_ordelo_service_key": "service-key",
        "llm_model": "gpt-test",
        "llm_openai_api_key": "test-key",
        "ms_stripe_url": "https://payments.test",
        "ms_stripe_token": "payment-token",
        "ms_stripe_reservation_url": "https://reservations.test",
        "ms_pricing_url": "https://pricing.test",
        "google_service_account_email": "maps@example.test",
        "google_service_account_encoded_credentials": "encoded",
        "google_service_account_maps_api_key": "maps-key",
        "bnat_waa_account_id": "bnat-account",
        "bnat_waa_business_account_id": "bnat-business",
        "bnat_waa_token": "bnat-token",
        "bnat_waa_phone_id": 123,
        "bnat_waa_callback_url": "https://bnat.test/callback",
        "bnat_waa_verify_token": "verify",
        "bnat_waa_app_id": "bnat-app",
        "bnat_waa_app_secret": "bnat-secret",
        "bnat_waa_private_key_password": "password",
        "sfcs_waa_account_id": "sfcs-account",
        "ordelo_web_key": "w" * 40,
    }


def test_load_settings_bundle_fetches_once_and_selects_exact_namespace(monkeypatch):
    calls = []
    database_client = object()

    def fake_get_agent_env(*, secret_name):
        calls.append(secret_name)
        return _secret_values()

    monkeypatch.setattr(bundle_module, "get_agent_env", fake_get_agent_env)
    monkeypatch.setattr(
        bundle_module.PgSetting,
        "client",
        property(lambda self: database_client),
    )

    settings = bundle_module.load_settings_bundle(
        RestaurantIdentity("BNAT", "bnat")
    )

    assert calls == ["restaurant-agents-env"]
    assert settings.project.rest_ref == "BNAT"
    assert settings.database_client is database_client
    assert settings.waba.waa_account_id == "bnat-account"
    assert settings.waba.waa_app_id == "bnat-app"
    assert settings.ordelo.web_key == "w" * 40


def test_server_database_clients_use_service_credentials(monkeypatch):
    from restaurant_agent_runtime.config import pg_setting

    calls = []
    def client(url, key):
        calls.append((url, key))
        return object()
    monkeypatch.setattr(pg_setting, "create_client", client)
    monkeypatch.setattr(pg_setting, "create_async_client", client)
    settings = pg_setting.PgSetting(**_secret_values())
    assert settings.client is not None
    assert settings.async_client is not None
    assert calls == [("https://example.supabase.co", "service-key")] * 2
    assert settings.headers["Authorization"] == "Bearer service-key"
