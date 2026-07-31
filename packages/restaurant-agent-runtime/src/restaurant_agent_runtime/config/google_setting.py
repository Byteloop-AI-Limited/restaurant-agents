"""Google settings model constructed at the application composition root."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import Field


class GoogleSettings(BaseSettings):
    email: str = Field(..., alias="google_service_account_email")
    encoded_credentials: str = Field(
        ..., alias="google_service_account_encoded_credentials"
    )
    maps_api_key: str = Field(..., alias="google_service_account_maps_api_key")

    model_config = SettingsConfigDict(extra="allow")

    def get_client(self):
        """Return the disabled Sheets placeholder retained by the source project."""

        return "dummy"
