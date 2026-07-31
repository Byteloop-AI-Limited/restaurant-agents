"""Project settings model constructed at the application composition root."""

import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger
from pydantic import Field

# %%


def get_project_root():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)))


class ProjectSetting(BaseSettings):
    salt: str = Field(..., alias="project_settings_salt")
    rest_ref: str = Field(..., alias="project_settings_rest_ref")

    def get_ordelo_url(self, client: Any) -> str:
        op = (
            client.table("ordelo_config")
            .select("config_value")
            .eq("config_key", "ORDELO_APP_URL")
            .execute()
        )
        data = getattr(op, "data", None)
        if not data:
            logger.error("ORDELO_APP_URL missing in ordelo_config response")
            raise ValueError("ORDELO_APP_URL not found in ordelo_config")
        value = data[0].get("config_value")
        if not value:
            logger.error("ORDELO_APP_URL missing config_value")
            raise ValueError("ORDELO_APP_URL missing config_value")
        return value

    @property
    def project_root(self) -> str:
        return get_project_root()

    model_config = SettingsConfigDict(extra="allow")
