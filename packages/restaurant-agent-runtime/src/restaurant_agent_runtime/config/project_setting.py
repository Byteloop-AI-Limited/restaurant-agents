"""Project settings model constructed at the application composition root."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# %%


def get_project_root():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)))


class ProjectSetting(BaseSettings):
    salt: str = Field(..., alias="project_settings_salt")
    rest_ref: str = Field(..., alias="project_settings_rest_ref")

    @property
    def project_root(self) -> str:
        return get_project_root()

    model_config = SettingsConfigDict(extra="allow")
