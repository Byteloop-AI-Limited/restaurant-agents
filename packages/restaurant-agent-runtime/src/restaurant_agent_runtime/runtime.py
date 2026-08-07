"""Explicit runtime contracts shared by restaurant applications."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from restaurant_agent_runtime.services.operational_lookup_cache import (
    OperationalLookupCache,
)


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
class EnquiryOption:
    """One app-owned triage enquiry button and its canonical intent."""

    title: str
    human_message: str

    def __post_init__(self) -> None:
        title = self.title.strip()
        human_message = self.human_message.strip()
        if not title or not human_message:
            raise ValueError("Enquiry option title and human_message must not be empty")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "human_message", human_message)


@dataclass(frozen=True, slots=True)
class EnquiryMenu:
    """App-owned WhatsApp menu shown for non-order enquiries."""

    prompt: str
    options: tuple[EnquiryOption, ...]

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        options = tuple(self.options)
        if not prompt:
            raise ValueError("Enquiry menu prompt must not be empty")
        if not 1 <= len(options) <= 3:
            raise ValueError("Enquiry menu must contain between one and three options")
        if len({option.title.casefold() for option in options}) != len(options):
            raise ValueError("Enquiry menu option titles must be unique")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "options", options)


DEFAULT_ENQUIRY_MENU = EnquiryMenu(
    prompt="What would you like help with?",
    options=(
        EnquiryOption("Share feedback", "I want to share feedback"),
        EnquiryOption("Parking availability", "I want to know about parking availability"),
        EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
    ),
)


@dataclass(frozen=True, slots=True)
class RestaurantPresentation:
    """Restaurant-owned customer-facing wording used by reusable services."""

    display_name: str
    contact_phone: str | None = None
    logo_url: str | None = None
    delivery_button_label: str = "Delivery"
    takeaway_button_label: str = "Takeaway"
    enquiry_menu: EnquiryMenu = DEFAULT_ENQUIRY_MENU


@dataclass(frozen=True, slots=True)
class RestaurantSettingsBundle:
    """Settings and external clients required by one restaurant runtime."""

    project: Any
    database: Any
    database_client: Any
    llm: Any
    payment: Any
    maps: Any
    waba: Any


@dataclass(frozen=True, slots=True)
class RestaurantRuntime:
    """All mutable external capabilities for exactly one restaurant app."""

    identity: RestaurantIdentity
    presentation: RestaurantPresentation
    settings: RestaurantSettingsBundle
    async_wa_client: Any
    sync_wa_client: Any
    operational_lookups: OperationalLookupCache


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
