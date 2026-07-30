"""
Unit tests for offline mode router helpers
    . Loads offline_mode with stubbed WhatsApp clients and config
    . Avoids creating real WhatsApp clients or updating real callback URLs
    . Covers offline replies, callback URL toggling, already-offline branch, and details endpoint
  Functions/Classes:
    . FakeAsyncWhatsApp
    . FakeSyncWhatsApp
    . offline_module
    . test_handle_offline_message_replies_with_notice
    . test_set_offline_mode_with_explicit_base_url
    . test_set_offline_mode_uses_existing_callback_and_already_offline_branch
    . test_get_details_returns_stubbed_wa_config
"""

from types import ModuleType, SimpleNamespace

import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeAsyncWhatsApp:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.handlers = []
        FakeAsyncWhatsApp.instances.append(self)

    def add_handlers(self, *handlers):
        self.handlers.extend(handlers)

    async def get_business_phone_number(self):
        return SimpleNamespace(
            display_phone_number="+44 7000 000001",
            verified_name="Elai",
            webhook_configuration={"application": "https://app.test/offline-mode"},
        )


class FakeSyncWhatsApp:
    def __init__(self):
        self.callback_url = "https://app.test/webhook"
        self.overrides = []

    def get_business_phone_number(self):
        return SimpleNamespace(
            webhook_configuration={"whatsapp_business_account": self.callback_url}
        )

    def override_waba_callback_url(self, **kwargs):
        self.overrides.append(kwargs)
        self.callback_url = kwargs["callback_url"]


@pytest.fixture
def offline_module(monkeypatch):
    config_stub = build_config_stub()
    sync_wa = FakeSyncWhatsApp()
    config_stub.waba_business_settings = SimpleNamespace(
        waa_token="token",
        waa_verify_token="verify",
        waa_phone_id="phone-id",
        private_key="private-key",
        waa_private_key_password_value="password",
        waa_account_id="account-id",
        waa_callback_url="https://app.test/webhook",
        create_wa_sync=lambda: sync_wa,
    )

    pywa_handlers = ModuleType("pywa.handlers")

    class MessageHandler:
        def __init__(self, callback):
            self.callback = callback

    pywa_handlers.MessageHandler = MessageHandler

    pywa_async = ModuleType("pywa_async")
    pywa_async.WhatsApp = FakeAsyncWhatsApp

    pywa = ModuleType("pywa")
    pywa.WhatsApp = FakeSyncWhatsApp

    module = load_module(
        "test_offline_mode_module",
        "restaurant_agent_runtime.watomation/routers/offline_mode.py",
        monkeypatch,
        {
            "config": config_stub,
            "pywa.handlers": pywa_handlers,
            "pywa_async": pywa_async,
            "pywa": pywa,
        },
    )
    module._sync_wa = sync_wa
    return module


@pytest.mark.asyncio
async def test_handle_offline_message_replies_with_notice(offline_module):
    replies = []
    msg = SimpleNamespace(reply=lambda text: _reply(replies, text))

    async def _reply(target, text):
        target.append(text)

    await offline_module.handle_offline_message(None, msg)

    assert replies == ["Apologies, we are currently offline. Please try again later."]


def test_set_offline_mode_with_explicit_base_url(offline_module):
    result = offline_module.set_offline_mode(enable=True, base_url="https://app.test/")

    assert result == {
        "offline_mode": True,
        "callback_url": "https://app.test/offline-mode",
    }
    assert offline_module._sync_wa.overrides[-1]["callback_url"] == "https://app.test/offline-mode"

    result = offline_module.set_offline_mode(enable=False, base_url="https://app.test/offline-mode")
    assert result == {"offline_mode": False, "callback_url": "https://app.test/offline-mode"}


def test_set_offline_mode_uses_existing_callback_and_already_offline_branch(offline_module):
    offline_module._sync_wa.callback_url = "https://app.test/webhook"
    result = offline_module.set_offline_mode(enable=True)
    assert result["callback_url"] == "https://app.test/webhook/offline-mode"

    result = offline_module.set_offline_mode(enable=True)
    assert result == {
        "offline_mode": True,
        "callback_url": "https://app.test/webhook/offline-mode",
        "message": "Already in offline mode",
    }


@pytest.mark.asyncio
async def test_get_details_returns_stubbed_wa_config(offline_module):
    details = await offline_module.get_details()

    assert details == {
        "phone_id": "phone-id",
        "display_phone_num": "+44 7000 000001",
        "verified_name": "Elai",
        "callback_url": "https://app.test/webhook",
        "callback_url_on_waba": "https://app.test/offline-mode",
        "llm_model": "gpt-test",
    }
