"""Namespaced WhatsApp Business configuration without process-global clients."""

# %%
import base64
from typing import Any

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pywa import WhatsApp as WhatsAppSync
from pywa_async import WhatsApp

# %%

WABA_VALIDATE_UPDATES = True


class WabaBusinessSettings(BaseSettings):
    waa_account_id: str
    waa_business_account_id: str
    waa_token: str
    waa_phone_id: int
    waa_callback_url: str
    waa_verify_token: str
    waa_app_id: str
    waa_app_secret: str
    waa_private_key_password_value: str = Field(alias="waa_private_key_password")
    waa_private_key_base64: str | None = None

    model_config = SettingsConfigDict(extra="ignore")

    @classmethod
    def for_namespace(
        cls, namespace: str, env_values: dict[str, Any] | None = None
    ) -> "WabaBusinessSettings":
        """Load one exact namespace and never fall back to another account."""

        normalized = namespace.strip().lower()
        if not normalized:
            raise ValueError("WABA namespace must not be empty")
        prefix = f"{normalized}_"
        if env_values is None:
            return cls(_env_prefix=prefix)

        remapped = {
            key[len(prefix) :]: value
            for key, value in env_values.items()
            if key.lower().startswith(prefix)
        }
        return cls(**remapped)

    def create_async_client(self, *, server: Any) -> WhatsApp:
        """Create the single server-bound, signature-validating async client."""

        return WhatsApp(
            token=self.waa_token,
            server=server,
            verify_token=self.waa_verify_token,
            phone_id=self.waa_phone_id,
            app_id=self.waa_app_id,
            app_secret=self.waa_app_secret,
            validate_updates=WABA_VALIDATE_UPDATES,
            continue_handling=False,
            business_private_key_password=self.waa_private_key_password_value,
        )

    def create_sync_client(self) -> WhatsAppSync:
        return WhatsAppSync(
            token=self.waa_token,
            business_account_id=self.waa_account_id,
            verify_token=self.waa_verify_token,
            phone_id=self.waa_phone_id,
            app_id=self.waa_app_id,
            app_secret=self.waa_app_secret,
        )

    @property
    def private_key(self) -> str:
        if not self.waa_private_key_base64:
            raise ValueError("waa_private_key_base64 is required")
        try:
            return base64.b64decode(self.waa_private_key_base64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error(f"Failed to decode WABA private key: {exc}")
            raise ValueError("waa_private_key_base64 is invalid") from exc

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.waa_token}",
        }
