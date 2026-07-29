from types import SimpleNamespace

import pytest

from restaurant_agent_core import RestaurantIdentity
from restaurant_agent_core.waba_callback import (
    CallbackValidationError,
    build_runtime_details,
    mask_secret,
    override_waba_callback_url,
    resolve_effective_callback_url,
    runtime_waba_details,
    validate_callback_update,
    validate_runtime_details,
    validate_token_app_binding,
    validate_waba_phone_binding,
)


def _settings():
    return SimpleNamespace(
        waa_account_id="waba-1234",
        waa_phone_id="phone-5678",
        waa_app_id="123456",
        waa_token="token-sensitive-9012",
        waa_verify_token="verify-sensitive-3456",
        waa_app_secret="secret-sensitive-7890",
        waa_callback_url="https://configured.test/",
    )


class FakeResponse:
    def __init__(self, data, *, error=False):
        self.data = data
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise RuntimeError("request failed")

    def json(self):
        return self.data


def test_runtime_details_masks_credentials_with_only_four_character_suffixes():
    settings = _settings()

    details = runtime_waba_details(RestaurantIdentity("BNAT", "bnat"), settings)

    assert details == {
        "rest_ref": "BNAT",
        "waba_namespace": "bnat",
        "waba_id": "waba-1234",
        "phone_id": "phone-5678",
        "app_id": "123456",
        "token_hint": "****9012",
        "app_secret_hint": "****7890",
        "validate_updates": True,
    }
    assert mask_secret("tiny") == "****"


def test_runtime_details_mismatch_names_fields_without_exposing_values():
    expected = runtime_waba_details(RestaurantIdentity("BNAT", "bnat"), _settings())
    actual = {**expected, "app_id": "different-app", "token_hint": "****0000"}

    with pytest.raises(CallbackValidationError) as exc_info:
        validate_runtime_details(expected, actual)

    message = str(exc_info.value)
    assert "app_id" in message
    assert "token_hint" in message
    assert "different-app" not in message
    assert "0000" not in message


@pytest.mark.parametrize(
    ("configuration", "expected"),
    [
        (
            {
                "phone_number": "https://phone.test/",
                "whatsapp_business_account": "https://waba.test/",
                "application": "https://app.test/",
            },
            "https://phone.test/",
        ),
        (
            {
                "whatsapp_business_account": "https://waba.test/",
                "application": "https://app.test/",
            },
            "https://waba.test/",
        ),
        ({"application": "https://app.test/"}, "https://app.test/"),
        ({}, None),
        (None, None),
    ],
)
def test_effective_callback_uses_meta_override_precedence(configuration, expected):
    assert resolve_effective_callback_url(configuration) == expected


async def test_enriched_details_returns_sanitized_partial_result(monkeypatch):
    settings = _settings()

    class UnavailableWhatsApp:
        async def get_business_phone_number(self, **kwargs):
            raise RuntimeError("meta-sensitive-error")

    def unavailable_restaurant(_):
        raise RuntimeError("database-sensitive-error")

    monkeypatch.setattr(
        "restaurant_agent_core.waba_callback._restaurant_master_details",
        unavailable_restaurant,
    )
    runtime = SimpleNamespace(
        identity=RestaurantIdentity("BNAT", "bnat"),
        settings=SimpleNamespace(waba=settings),
        async_wa_client=UnavailableWhatsApp(),
    )

    details = await build_runtime_details(runtime)

    assert details["display_number"] is None
    assert details["admins"] is None
    assert details["service_hours"] is None
    assert details["callback_url"] is None
    assert details["configured_callback_url"] == "https://configured.test/"
    assert details["details_errors"] == {
        "meta": "unavailable",
        "restaurant_master": "unavailable",
    }
    serialized = str(details)
    assert "meta-sensitive-error" not in serialized
    assert "database-sensitive-error" not in serialized
    assert settings.waa_token not in serialized
    assert settings.waa_app_secret not in serialized


def test_token_app_binding_checks_app_pair_and_issuing_app_without_leaking_secrets():
    settings = _settings()
    app_token_calls = []
    request_calls = []

    class Client:
        def get_app_access_token(self, **kwargs):
            app_token_calls.append(kwargs)
            return "temporary-app-access-token"

    def request_get(url, **kwargs):
        request_calls.append((url, kwargs))
        return FakeResponse({"data": {"is_valid": True, "app_id": "123456"}})

    validate_token_app_binding(Client(), settings, request_get=request_get)

    assert app_token_calls == [
        {"app_id": 123456, "app_secret": "secret-sensitive-7890"}
    ]
    assert request_calls[0][1]["params"] == {"input_token": "token-sensitive-9012"}
    assert request_calls[0][1]["headers"] == {
        "Authorization": "Bearer temporary-app-access-token"
    }


@pytest.mark.parametrize(
    ("token_data", "expected_message"),
    [
        ({"is_valid": False, "app_id": "123456"}, "not valid"),
        ({"is_valid": True, "app_id": "654321"}, "different Meta app"),
    ],
)
def test_token_app_binding_fails_before_write_for_invalid_or_wrong_app_token(
    token_data, expected_message
):
    class Client:
        def get_app_access_token(self, **kwargs):
            return "temporary-app-access-token"

    with pytest.raises(CallbackValidationError, match=expected_message):
        validate_token_app_binding(
            Client(),
            _settings(),
            request_get=lambda *args, **kwargs: FakeResponse({"data": token_data}),
        )


def test_token_app_binding_rejects_invalid_app_pair_without_leaking_secret():
    class Client:
        def get_app_access_token(self, **kwargs):
            raise RuntimeError("secret-sensitive-7890")

    with pytest.raises(CallbackValidationError) as exc_info:
        validate_token_app_binding(Client(), _settings())

    assert "could not obtain" in str(exc_info.value)
    assert "secret-sensitive-7890" not in str(exc_info.value)


def test_waba_phone_binding_requires_selected_phone_in_selected_waba():
    class Client:
        def get_business_phone_numbers(self, **kwargs):
            assert kwargs == {"waba_id": "waba-1234"}
            return [SimpleNamespace(id="phone-other")]

    with pytest.raises(CallbackValidationError, match="does not belong"):
        validate_waba_phone_binding(Client(), _settings())


def test_waba_phone_binding_accepts_selected_phone_in_selected_waba():
    class Client:
        def get_business_phone_numbers(self, **kwargs):
            return [SimpleNamespace(id="phone-5678")]

    validate_waba_phone_binding(Client(), _settings())


def test_override_uses_exact_selected_namespace_values():
    calls = []

    class Client:
        def override_waba_callback_url(self, **kwargs):
            calls.append(kwargs)
            return True

    result = override_waba_callback_url(Client(), _settings(), "https://target.test/")

    assert result is True
    assert calls == [
        {
            "callback_url": "https://target.test/",
            "verify_token": "verify-sensitive-3456",
            "waba_id": "waba-1234",
        }
    ]


def _subscriptions(callback_url="https://target.test/"):
    return {
        "data": [
            {
                "whatsapp_business_api_data": {
                    "id": "123456",
                },
                "override_callback_uri": callback_url,
            }
        ]
    }


def test_callback_update_accepts_matching_waba_and_effective_phone_configuration():
    validate_callback_update(
        settings=_settings(),
        callback_url="https://target.test/",
        subscriptions=_subscriptions("https://target.test"),
        webhook_configuration={
            "application": "https://base-app.test/",
            "whatsapp_business_account": "https://target.test/",
            "phone_number": "https://target.test",
        },
    )


@pytest.mark.parametrize(
    ("subscriptions", "webhook_configuration", "expected_message"),
    [
        ({"data": []}, {}, "not subscribed"),
        (_subscriptions("https://wrong.test"), {}, "does not match"),
        (
            _subscriptions(),
            {"phone_number": "https://wrong.test"},
            "higher-precedence phone callback override",
        ),
    ],
)
def test_callback_update_rejects_subscription_and_override_mismatches(
    subscriptions, webhook_configuration, expected_message
):
    with pytest.raises(CallbackValidationError, match=expected_message):
        validate_callback_update(
            settings=_settings(),
            callback_url="https://target.test/",
            subscriptions=subscriptions,
            webhook_configuration=webhook_configuration,
        )
