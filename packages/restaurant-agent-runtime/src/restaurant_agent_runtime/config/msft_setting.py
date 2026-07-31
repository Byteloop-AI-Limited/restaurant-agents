"""Microsoft Azure AD settings model with explicit client construction."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from msal import ConfidentialClientApplication
from pydantic import Field


class MsftSettings(BaseSettings):
    tenant_id: str = Field(..., alias="bloop_ms_tenant_id")
    client_id: str = Field(..., alias="bloop_ms_client_id")
    client_secret: str = Field(..., alias="bloop_ms_client_secret")

    @property
    def access_token(self) -> str:
        app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority="https://login.microsoftonline.com/common",
        )
        scope = "https://graph.microsoft.com/.default"
        result = app.acquire_token_for_client(scopes=[scope])

        if "access_token" in result:
            return result["access_token"]
        else:
            error_message = result.get("error_description", "Unknown error")
            error_code = result.get("error", "No error code available")
            print(f"Error {error_code}: {error_message}")
            raise Exception(f"Failed to obtain access token: {error_message}")

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    model_config = SettingsConfigDict(extra="allow")
