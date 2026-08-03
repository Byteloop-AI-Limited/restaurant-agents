"""Import-safe configuration entry points.

Settings and external clients are built only by ``load_settings_bundle`` and
flow through ``RestaurantRuntime``. Logging remains process-local and does not
load application configuration.
"""

from importlib import import_module
from typing import Any

__all__ = ["WabaBusinessSettings", "load_settings_bundle", "logger"]


def __getattr__(name: str) -> Any:
    if name == "logger":
        return import_module(f"{__name__}.logger_setting").logger
    if name == "WabaBusinessSettings":
        return import_module(f"{__name__}.waba_setting").WabaBusinessSettings
    if name == "load_settings_bundle":
        return import_module(f"{__name__}.bundle").load_settings_bundle
    raise AttributeError(name)
