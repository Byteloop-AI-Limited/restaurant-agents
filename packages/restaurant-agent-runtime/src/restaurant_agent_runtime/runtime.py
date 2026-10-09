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


# SectionRow.callback_data caps at 200 (Meta); pywa does not validate this
# client-side, so an over-length payload fails silently at send time for the
# one customer who taps that row. The /SelectEnquiry JSON envelope (action +
# rest_ref + active_agent + quoting) measures 90 chars with a 4-char
# rest_ref, leaving 110 — cap human_message at 100 for headroom.
_ENQUIRY_HUMAN_MESSAGE_MAX_LENGTH = 100


@dataclass(frozen=True, slots=True)
class EnquiryOption:
    """One app-owned enquiry topic, rendered as a WhatsApp SectionList row."""

    title: str
    human_message: str
    description: str | None = None
    only_for_rest_refs: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        title = self.title.strip()
        human_message = self.human_message.strip()
        description = (self.description or "").strip() or None
        if not title or not human_message:
            raise ValueError("Enquiry option title and human_message must not be empty")
        if len(title) > 24:
            raise ValueError("Enquiry option title must be at most 24 characters")
        if len(human_message) > _ENQUIRY_HUMAN_MESSAGE_MAX_LENGTH:
            raise ValueError(
                "Enquiry option human_message must be at most "
                f"{_ENQUIRY_HUMAN_MESSAGE_MAX_LENGTH} characters"
            )
        if description is not None and len(description) > 72:
            raise ValueError("Enquiry option description must be at most 72 characters")
        only_for_rest_refs = self.only_for_rest_refs
        if only_for_rest_refs is not None:
            only_for_rest_refs = tuple(ref.strip().upper() for ref in only_for_rest_refs)
            if not only_for_rest_refs:
                raise ValueError(
                    "Enquiry option only_for_rest_refs must not be an empty tuple "
                    "(omit it, or pass None, to show the option for every brand)"
                )
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "human_message", human_message)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "only_for_rest_refs", only_for_rest_refs)

    def is_visible_for(self, rest_ref: str | None) -> bool:
        """Return whether this row should render for the given selected brand."""
        if self.only_for_rest_refs is None:
            return True
        if rest_ref is None:
            return False
        return rest_ref.strip().upper() in self.only_for_rest_refs


@dataclass(frozen=True, slots=True)
class EnquiryMenu:
    """App-owned WhatsApp SectionList shown for non-order enquiries."""

    prompt: str
    options: tuple[EnquiryOption, ...]
    button_title: str = "Options"

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        options = tuple(self.options)
        button_title = self.button_title.strip()
        if not prompt:
            raise ValueError("Enquiry menu prompt must not be empty")
        if not 1 <= len(options) <= 10:
            raise ValueError("Enquiry menu must contain between one and ten options")
        if len({option.title.casefold() for option in options}) != len(options):
            raise ValueError("Enquiry menu option titles must be unique")
        if not button_title:
            raise ValueError("Enquiry menu button_title must not be empty")
        if len(button_title) > 20:
            raise ValueError("Enquiry menu button_title must be at most 20 characters")
        if not any(option.only_for_rest_refs is None for option in options):
            raise ValueError(
                "Enquiry menu must contain at least one option visible to every "
                "brand (only_for_rest_refs=None), so a customer whose brand is "
                "unknown or restricted from every row still sees a non-empty menu"
            )
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "options", options)
        object.__setattr__(self, "button_title", button_title)

    def visible_options_for(self, rest_ref: str | None) -> tuple[EnquiryOption, ...]:
        """Return the options that should render for the given selected brand."""
        return tuple(option for option in self.options if option.is_visible_for(rest_ref))


DEFAULT_ENQUIRY_OPTIONS = (
    EnquiryOption("Share feedback", "I want to share feedback"),
    EnquiryOption("Parking availability", "I want to know about parking availability"),
    EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
)

DEFAULT_ENQUIRY_MENU = EnquiryMenu(
    prompt="What would you like help with?",
    options=DEFAULT_ENQUIRY_OPTIONS,
)

DEFAULT_DELIVERY_PROMO_CAPTION = "Limited Time Offer - 20% off on all delivery orders"
DEFAULT_TAKEAWAY_PROMO_CAPTION = "Get started with your collection order"


@dataclass(frozen=True, slots=True)
class RestaurantChoice:
    """One selectable restaurant brand behind a single multi-restaurant app."""

    rest_ref: str
    title: str
    display_name: str
    human_message: str
    logo_url: str | None = None
    supports_dine_in: bool = True
    delivery_promo_caption: str | None = None
    takeaway_promo_caption: str | None = None
    delivery_button_label: str | None = None
    takeaway_button_label: str | None = None

    def __post_init__(self) -> None:
        rest_ref = self.rest_ref.strip().upper()
        title = self.title.strip()
        display_name = self.display_name.strip()
        human_message = self.human_message.strip()
        if not rest_ref:
            raise ValueError("RestaurantChoice rest_ref must not be empty")
        if not title:
            raise ValueError("RestaurantChoice title must not be empty")
        if len(title) > 20:
            raise ValueError("RestaurantChoice title must be at most 20 characters")
        if not display_name:
            raise ValueError("RestaurantChoice display_name must not be empty")
        if not human_message:
            raise ValueError("RestaurantChoice human_message must not be empty")
        # WhatsApp interactive button titles cap at 20 characters; these
        # override RestaurantPresentation's own already-validated labels.
        if self.delivery_button_label is not None and len(self.delivery_button_label) > 20:
            raise ValueError(
                "RestaurantChoice delivery_button_label must be at most 20 characters"
            )
        if self.takeaway_button_label is not None and len(self.takeaway_button_label) > 20:
            raise ValueError(
                "RestaurantChoice takeaway_button_label must be at most 20 characters"
            )
        object.__setattr__(self, "rest_ref", rest_ref)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "human_message", human_message)


@dataclass(frozen=True, slots=True)
class RestaurantSelection:
    """App-owned configuration for a restaurant-selection gate before ordering.

    Only apps that serve more than one restaurant brand behind one WhatsApp
    number configure this. Its absence (the default on `RestaurantPresentation`)
    leaves every selection-aware code path inert.
    """

    prompt: str
    choices: tuple[RestaurantChoice, ...]

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        choices = tuple(self.choices)
        if not prompt:
            raise ValueError("Restaurant selection prompt must not be empty")
        if not 2 <= len(choices) <= 3:
            raise ValueError("Restaurant selection must contain two or three choices")
        if len({choice.rest_ref for choice in choices}) != len(choices):
            raise ValueError("Restaurant selection choices must have unique rest_ref values")
        if len({choice.title.casefold() for choice in choices}) != len(choices):
            raise ValueError("Restaurant selection choice titles must be unique")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "choices", choices)

    def choice_for(self, rest_ref: str | None) -> RestaurantChoice | None:
        """Return the configured choice matching `rest_ref`, if any."""
        if not rest_ref:
            return None
        normalized = rest_ref.strip().upper()
        for choice in self.choices:
            if choice.rest_ref == normalized:
                return choice
        return None


@dataclass(frozen=True, slots=True)
class RestaurantPresentation:
    """Restaurant-owned customer-facing wording used by reusable services."""

    display_name: str
    contact_phone: str | None = None
    logo_url: str | None = None
    delivery_button_label: str = "Delivery"
    takeaway_button_label: str = "Takeaway"
    enquiry_button_label: str = "More options"
    enquiry_menu: EnquiryMenu = DEFAULT_ENQUIRY_MENU
    restaurant_selection: "RestaurantSelection | None" = None
    reservation_base_url: str | None = None
    delivery_promo_caption: str = DEFAULT_DELIVERY_PROMO_CAPTION
    takeaway_promo_caption: str = DEFAULT_TAKEAWAY_PROMO_CAPTION

    def __post_init__(self) -> None:
        # WhatsApp interactive button titles cap at 20 characters.
        if len(self.delivery_button_label) > 20:
            raise ValueError(
                "RestaurantPresentation delivery_button_label must be at most 20 characters"
            )
        if len(self.takeaway_button_label) > 20:
            raise ValueError(
                "RestaurantPresentation takeaway_button_label must be at most 20 characters"
            )
        if len(self.enquiry_button_label) > 20:
            raise ValueError(
                "RestaurantPresentation enquiry_button_label must be at most 20 characters"
            )


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
    ordelo: Any = None  # OrdeloSetting; None in tests that don't need it


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
