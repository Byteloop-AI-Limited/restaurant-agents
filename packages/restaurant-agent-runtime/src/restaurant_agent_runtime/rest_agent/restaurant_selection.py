"""Single owner of the restaurant-selection projection for multi-restaurant apps.

Most restaurant apps serve exactly one restaurant and never configure
`RestaurantPresentation.restaurant_selection`; every function here is a no-op
in that case. A small number of apps (for example ELAS) serve more than one
restaurant brand behind one WhatsApp number and must ask the customer which
one they mean before any ordering flow starts. `state["selected_rest_ref"]` is
that customer choice; `state["rest_ref"]` remains the invariant app identity
and must never be read as a substitute — it is always seeded on new threads,
so falling back to it would make the gate believe a restaurant was already
chosen.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from restaurant_agent_runtime.runtime import RestaurantChoice, RestaurantSelection


def selected_choice(
    state: Mapping[str, Any], selection: RestaurantSelection | None
) -> RestaurantChoice | None:
    """Return the customer's chosen restaurant, if selection is configured and known."""
    if selection is None:
        return None
    return selection.choice_for(state.get("selected_rest_ref"))


def selection_pending(
    state: Mapping[str, Any], selection: RestaurantSelection | None
) -> bool:
    """Return whether a configured selection has not yet been made."""
    if selection is None:
        return False
    return selected_choice(state, selection) is None


def resolve_menu_rest_ref(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the rest_ref that should drive the menu link and CTA image."""
    choice = selected_choice(state, selection)
    return choice.rest_ref if choice is not None else fallback


def resolve_menu_logo_url(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the logo URL that should accompany the menu CTA."""
    choice = selected_choice(state, selection)
    if choice is not None and choice.logo_url:
        return choice.logo_url
    return fallback


def resolve_delivery_promo_caption(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the delivery menu caption, preferring the selected brand's override."""
    choice = selected_choice(state, selection)
    if choice is not None and choice.delivery_promo_caption:
        return choice.delivery_promo_caption
    return fallback


def resolve_takeaway_promo_caption(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the takeaway menu caption, preferring the selected brand's override."""
    choice = selected_choice(state, selection)
    if choice is not None and choice.takeaway_promo_caption:
        return choice.takeaway_promo_caption
    return fallback


def resolve_delivery_button_label(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the delivery service-selection button label for the selected brand."""
    choice = selected_choice(state, selection)
    if choice is not None and choice.delivery_button_label:
        return choice.delivery_button_label
    return fallback


def resolve_takeaway_button_label(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    fallback: str,
) -> str:
    """Return the takeaway service-selection button label for the selected brand."""
    choice = selected_choice(state, selection)
    if choice is not None and choice.takeaway_button_label:
        return choice.takeaway_button_label
    return fallback


def dinein_available(
    state: Mapping[str, Any],
    selection: RestaurantSelection | None,
    reservation_base_url: str | None,
) -> bool:
    """Return whether the dine-in node is usable for the current customer.

    False when this app has no reservation link configured at all, or when a
    multi-restaurant app's customer has chosen a brand whose
    `RestaurantChoice.supports_dine_in` is `False` (for example, a takeaway-only
    brand behind the same WhatsApp number).
    """
    if not reservation_base_url:
        return False
    choice = selected_choice(state, selection)
    if choice is not None and not choice.supports_dine_in:
        return False
    return True


async def selection_required_block(ctx: Any, tool_call_id: str) -> Command:
    """Block a specialist transfer and ask which restaurant the customer means.

    Sends the same restaurant-selection buttons as `ask_user_to_select_restaurant`
    directly, ending the current node's own turn (`goto=END`), rather than
    redirecting through a parent-graph `Command` plus a `SystemMessage`
    instruction for the model to call that tool itself. A tool that crosses
    back out to `Command.PARENT` while the model's own tool-call message is
    still pending can leave the checkpointed message tail out of order (the
    redirect lands before its own `ToolMessage`), which the runtime's
    tail-repair logic misreads as a genuinely missing tool response. Mirrors
    `ask_user_to_select_restaurant` and `retained_handoff_block`, both of
    which use this same shape in production.
    """
    from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
        select_restaurant_wa_send,
    )

    await select_restaurant_wa_send(
        recipient=ctx.recipient,
        wa_client=ctx.wa_client,
        selection=ctx.restaurant_selection,
    )
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    content=(
                        "Transfer redirected: no restaurant has been selected yet."
                    ),
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Please select a restaurant."),
            ],
        },
    )


__all__ = [
    "selected_choice",
    "selection_pending",
    "resolve_menu_rest_ref",
    "resolve_menu_logo_url",
    "resolve_delivery_promo_caption",
    "resolve_takeaway_promo_caption",
    "resolve_delivery_button_label",
    "resolve_takeaway_button_label",
    "dinein_available",
    "selection_required_block",
]
