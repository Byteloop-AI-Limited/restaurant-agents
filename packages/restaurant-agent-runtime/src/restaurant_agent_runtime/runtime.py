"""Explicit runtime contracts shared by restaurant applications."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RestaurantIdentity:
    """Stable routing and secret-namespace identity for one application."""

    rest_ref: str
    waba_namespace: str

    def __post_init__(self) -> None:
        rest_ref = self.rest_ref.strip().upper()
        namespace = self.waba_namespace.strip().lower()
        if not rest_ref:
            raise ValueError("rest_ref must not be empty")
        if not namespace:
            raise ValueError("waba_namespace must not be empty")
        object.__setattr__(self, "rest_ref", rest_ref)
        object.__setattr__(self, "waba_namespace", namespace)

    def matches(self, rest_ref: str) -> bool:
        return rest_ref.strip().upper() == self.rest_ref


@dataclass(frozen=True, slots=True)
class RestaurantPresentation:
    """Restaurant-owned wording used by otherwise reusable services."""

    display_name: str
    contact_phone: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class RestaurantSettingsBundle:
    """Settings and external clients required by one restaurant runtime."""

    project: Any
    database: Any
    database_client: Any
    llm: Any
    payment: Any
    maps: Any
    microservices: Any
    waba: Any


@dataclass(frozen=True, slots=True)
class RestaurantRuntime:
    """All mutable external capabilities for exactly one restaurant app."""

    identity: RestaurantIdentity
    presentation: RestaurantPresentation
    settings: RestaurantSettingsBundle
    async_wa_client: Any
    sync_wa_client: Any


@runtime_checkable
class GraphAdapter(Protocol):
    """Restaurant-owned LangGraph operations consumed by shared webhooks."""

    async def run_rest_graph_with_custom_msg(self, recipient: str, **kwargs: Any) -> Any:
        ...

    async def debug_state(self, recipient: str, full_state: bool = False) -> dict:
        ...

    async def debug_state_values(
        self, recipient: str | None = None, config: dict | None = None
    ) -> dict:
        ...

    async def debug_state_by_thread(
        self, thread_id: str, full_state: bool = False
    ) -> dict:
        ...


GraphAdapterFactory = Callable[[RestaurantRuntime], GraphAdapter]
