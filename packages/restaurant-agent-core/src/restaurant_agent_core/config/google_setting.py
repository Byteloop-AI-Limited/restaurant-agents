"""
Google API settings and client configuration for the agent
  . Defines GoogleSettings for service account and API key management
  . Provides get_client method to instantiate gspread client for Google Sheets
  . Handles credential decoding from base64-encoded JSON
  . Authenticates using OAuth2 service account credentials
  . Loads configuration from AWS environment settings
  Functions/Classes:
    . GoogleSettings
    . google_settings
    . g_client
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from restaurant_agent_core.utils.aws_setting import agent_env
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


google_settings = GoogleSettings(**agent_env)
g_client = google_settings.get_client()

# %% Usage
# sheet =g_client.open("elai_takeaway_menu").sheet1
# sheet.get_all_records()

# %% How to create encoded creds
# with open(f'{project_setting.get_project_root()}/google_creds.json', "r") as file:
#     json_content = file.read()

# encoded_credentials = base64.b64encode(json_content.encode()).decode()
