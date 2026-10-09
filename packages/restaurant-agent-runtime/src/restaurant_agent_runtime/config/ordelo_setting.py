"""Ordelo (OrdeloAgent) service settings shared by every app in the project."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class OrdeloSetting(BaseSettings):
    # Same value as OrdeloAgent's ORDELO_WEB_KEY, from the shared AWS secret.
    # Empty means the receipt order-link feature is off.
    web_key: str = Field("", alias="ordelo_web_key")

    model_config = SettingsConfigDict(extra="allow")
