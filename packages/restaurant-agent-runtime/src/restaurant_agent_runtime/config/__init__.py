"""Lazy exports for shared configuration.

Importing :mod:`restaurant_agent_runtime` stays side-effect free. Legacy settings are
loaded only when a consumer requests them, while WhatsApp clients are never exposed
as globals and must come from ``RestaurantRuntime``.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "project_settings": ("project_setting", "project_settings"),
    "get_project_root": ("project_setting", "get_project_root"),
    "ms_settings": ("microservices_setting", "ms_settings"),
    "msft_settings": ("msft_setting", "msft_settings"),
    "google_settings": ("google_setting", "google_settings"),
    "g_client": ("google_setting", "g_client"),
    "stripe_settings": ("stripe_setting", "stripe_settings"),
    "pg_settings": ("pg_setting", "pg_settings"),
    "client": ("pg_setting", "client"),
    "client_ordelo": ("pg_setting", "client_ordelo"),
    "logger": ("logger_setting", "logger"),
    "llm_settings": ("llm_setting", "llm_settings"),
}

__all__ = [*_EXPORTS, "WabaBusinessSettings", "load_settings_bundle"]


def __getattr__(name: str) -> Any:
    if name == "WabaBusinessSettings":
        from .waba_setting import WabaBusinessSettings

        return WabaBusinessSettings
    if name == "load_settings_bundle":
        from .bundle import load_settings_bundle

        return load_settings_bundle
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, attribute)
