"""
Module-loading helpers for stubbed unit tests
    . Loads source files with injected sys.modules stubs
    . Prevents production config side effects while preserving source execution
  Functions/Classes:
    . load_module
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from tests._stubs.config_stub import build_config_stub


REPO_ROOT = Path(__file__).resolve().parents[2]

_SOURCE_PREFIXES = {
    "restaurant_agent_core.config/": "packages/restaurant-agent-core/src/restaurant_agent_core/config/",
    "restaurant_agent_core.services/": "packages/restaurant-agent-core/src/restaurant_agent_core/services/",
    "restaurant_agent_core.utils/": "packages/restaurant-agent-core/src/restaurant_agent_core/utils/",
    "restaurant_agent_core.watomation/": "packages/restaurant-agent-core/src/restaurant_agent_core/watomation/",
    "sfcs_agent.rest_agent/": "apps/sfcs/src/sfcs_agent/rest_agent/",
}

_MODULE_PREFIXES = {
    "config": "restaurant_agent_core.config",
    "services": "restaurant_agent_core.services",
    "utils": "restaurant_agent_core.utils",
    "watomation": "restaurant_agent_core.watomation",
    "rest_agent": "sfcs_agent.rest_agent",
}


def _migrated_source_path(relative_path: str) -> Path:
    for legacy, migrated in _SOURCE_PREFIXES.items():
        if relative_path.startswith(legacy):
            return REPO_ROOT / migrated / relative_path.removeprefix(legacy)
    return REPO_ROOT / relative_path


def _migrated_module_name(name: str) -> str | None:
    root, dot, suffix = name.partition(".")
    migrated_root = _MODULE_PREFIXES.get(root)
    if migrated_root is None:
        return None
    return migrated_root + (dot + suffix if dot else "")


def _build_dedup_stub():
    """Stub watomation.dedup so wa_dedup is a passthrough.

    SFCS handlers are decorated with @wa_dedup, which accesses `update.id`.
    Many ported tests use lightweight fakes without `.id`; this stub bypasses
    deduplication during unit tests.
    """
    module = ModuleType("restaurant_agent_core.watomation.dedup")

    def wa_dedup(fn):
        return fn

    module.wa_dedup = wa_dedup
    module._check_and_record = lambda _id: False
    return module


def load_module(module_name: str, relative_path: str, monkeypatch, stubs=None):
    module_stubs = {
        "restaurant_agent_core.config": build_config_stub(),
        "restaurant_agent_core.watomation.dedup": _build_dedup_stub(),
        **(stubs or {}),
    }
    for name, module in module_stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
        migrated_name = _migrated_module_name(name)
        if migrated_name is not None:
            monkeypatch.setitem(sys.modules, migrated_name, module)

    spec = importlib.util.spec_from_file_location(
        module_name,
        _migrated_source_path(relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
