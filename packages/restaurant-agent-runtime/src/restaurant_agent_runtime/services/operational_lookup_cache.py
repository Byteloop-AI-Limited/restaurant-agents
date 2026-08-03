"""Runtime-owned, process-local cache for non-transactional operational lookups."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from loguru import logger

if TYPE_CHECKING:
    from restaurant_agent_runtime.services.ordelo_service.datamodels.restaurant_master_pymodel import (
        RestaurantMaster,
    )


APP_URL_TTL_SECONDS = 60 * 60
RESTAURANT_MASTER_TTL_SECONDS = 5 * 60
OVERWATCH_TTL_SECONDS = 5 * 60

CacheScope = Literal["all", "operational_config", "restaurant_master", "overwatch"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class OperationalLookupCache:
    """Cache operational configuration for exactly one ``RestaurantRuntime``.

    This cache deliberately excludes transactional order, delivery, customer, and
    thread data. Failed and missing lookups are never cached, so a repair to the
    source of truth takes effect on the next request (or after an explicit reset).
    """

    def __init__(
        self,
        *,
        rest_ref: str,
        database_client: Any,
        app_url_ttl_seconds: float = APP_URL_TTL_SECONDS,
        restaurant_master_ttl_seconds: float = RESTAURANT_MASTER_TTL_SECONDS,
        overwatch_ttl_seconds: float = OVERWATCH_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rest_ref = rest_ref.strip().upper()
        self._database_client = database_client
        self._app_url_ttl_seconds = app_url_ttl_seconds
        self._restaurant_master_ttl_seconds = restaurant_master_ttl_seconds
        self._overwatch_ttl_seconds = overwatch_ttl_seconds
        self._clock = clock
        self._app_urls: dict[str, _CacheEntry[str]] = {}
        self._restaurant_master: _CacheEntry[RestaurantMaster] | None = None
        self._overwatch: _CacheEntry[frozenset[str]] | None = None
        self._lock_guard = Lock()
        self._locks: dict[tuple[str, str], Lock] = {}

    @property
    def rest_ref(self) -> str:
        return self._rest_ref

    def get_app_url(self, app_ref: str) -> str:
        """Return the configured application URL for this restaurant or Ordelo."""
        normalized_app_ref = self._normalize_app_ref(app_ref)
        entry = self._app_urls.get(normalized_app_ref)
        if entry is not None and entry.expires_at > self._clock():
            return entry.value

        with self._lock_for("app_url", normalized_app_ref):
            entry = self._app_urls.get(normalized_app_ref)
            if entry is not None and entry.expires_at > self._clock():
                return entry.value

            config_key = f"{normalized_app_ref}_APP_URL"
            value = self._read_config_value(config_key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"No config found for {config_key} in ordelo_config")
            self._app_urls[normalized_app_ref] = _CacheEntry(
                value=value.strip(),
                expires_at=self._clock() + self._app_url_ttl_seconds,
            )
            return value.strip()

    def get_restaurant_master(self) -> RestaurantMaster:
        """Return the current runtime restaurant's cached ``RestaurantMaster``."""
        entry = self._restaurant_master
        if entry is not None and entry.expires_at > self._clock():
            return entry.value

        with self._lock_for("restaurant_master", self._rest_ref):
            entry = self._restaurant_master
            if entry is not None and entry.expires_at > self._clock():
                return entry.value
            from restaurant_agent_runtime.services.ordelo_service.datamodels.restaurant_master_pymodel import (
                RestaurantMaster,
            )

            restaurant_master = RestaurantMaster.from_rest_ref(
                self._rest_ref,
                database_client=self._database_client,
            )
            self._restaurant_master = _CacheEntry(
                value=restaurant_master,
                expires_at=self._clock() + self._restaurant_master_ttl_seconds,
            )
            return restaurant_master

    def get_overwatch_recipients(self) -> frozenset[str]:
        """Return normalized recipients from the ``overwatch_list`` config value."""
        entry = self._overwatch
        if entry is not None and entry.expires_at > self._clock():
            return entry.value

        with self._lock_for("overwatch", self._rest_ref):
            entry = self._overwatch
            if entry is not None and entry.expires_at > self._clock():
                return entry.value
            value = self._read_config_value("overwatch_list")
            if not isinstance(value, str):
                raise ValueError("No config found for overwatch_list in ordelo_config")
            recipients = frozenset(
                recipient.strip().lstrip("+")
                for recipient in value.split(",")
                if recipient.strip().lstrip("+")
            )
            self._overwatch = _CacheEntry(
                value=recipients,
                expires_at=self._clock() + self._overwatch_ttl_seconds,
            )
            return recipients

    def is_overwatch_recipient(self, recipient: str | None) -> bool:
        """Return false if the source cannot be read; privileged access fails closed."""
        if not recipient:
            return False
        try:
            return recipient.strip().lstrip("+") in self.get_overwatch_recipients()
        except Exception:
            logger.exception("Could not read the Overwatch recipient allowlist")
            return False

    def reset(
        self,
        *,
        scope: CacheScope = "all",
        app_ref: str | None = None,
    ) -> dict[str, int]:
        """Clear selected entries and return counts without exposing cached values."""
        removed = {"operational_config": 0, "restaurant_master": 0, "overwatch": 0}
        if scope in ("all", "operational_config"):
            if app_ref is None:
                removed["operational_config"] = len(self._app_urls)
                self._app_urls.clear()
            else:
                normalized_app_ref = self._normalize_app_ref(app_ref)
                removed["operational_config"] = int(
                    self._app_urls.pop(normalized_app_ref, None) is not None
                )
        if scope in ("all", "restaurant_master"):
            removed["restaurant_master"] = int(self._restaurant_master is not None)
            self._restaurant_master = None
        if scope in ("all", "overwatch"):
            removed["overwatch"] = int(self._overwatch is not None)
            self._overwatch = None
        return removed

    def _normalize_app_ref(self, app_ref: str) -> str:
        normalized = app_ref.strip().upper()
        if normalized not in {self._rest_ref, "ORDELO", "RESTAURANT_MENU"}:
            raise ValueError(f"Unsupported application reference: {app_ref}")
        return normalized

    def _lock_for(self, category: str, key: str) -> Lock:
        lock_key = (category, key)
        with self._lock_guard:
            return self._locks.setdefault(lock_key, Lock())

    def _read_config_value(self, config_key: str) -> Any:
        response = (
            self._database_client.table("ordelo_config")
            .select("config_value")
            .eq("config_key", config_key)
            .limit(1)
            .execute()
        )
        data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
        if not data:
            raise ValueError(f"No config found for {config_key} in ordelo_config")
        return data[0].get("config_value")
