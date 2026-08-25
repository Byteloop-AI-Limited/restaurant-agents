"""Deterministic new-order service selection across WhatsApp adapters."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Command

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    select_restaurant_wa_send,
)
from restaurant_agent_runtime.rest_agent.new_order_entry import (
    send_new_order_closed_message,
    send_new_order_menu,
)
from restaurant_agent_runtime.rest_agent.restaurant_selection import (
    resolve_delivery_promo_caption,
    resolve_menu_logo_url,
    resolve_menu_rest_ref,
    resolve_takeaway_promo_caption,
    selection_pending,
    selection_required_block,
)
from restaurant_agent_runtime.rest_agent.specialist_lifecycle import (
    ServiceKind,
    SpecialistFlowView,
    new_specialist_flow_state,
    retained_completion_first_message,
)
from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.services.thread_management import ThreadHandler
from restaurant_agent_runtime.services.thread_management.graph_config import (
    get_config_for_recipient,
)

_NEGATED_OR_INFORMATIONAL = re.compile(
    r"\b(?:don't|do not|dont|cancel|where|when|why|how|is|are|do|does|"
    r"halal|status|track)\b",
    re.IGNORECASE,
)
_SERVICE_ALIASES: tuple[tuple[ServiceKind, re.Pattern[str]], ...] = (
    ("delivery", re.compile(r"\bdeliver(?:y|ed|ing)?\b", re.IGNORECASE)),
    (
        "takeaway",
        re.compile(r"\b(?:take\s*away|collection|collect|pickup|pick\s*up)\b", re.IGNORECASE),
    ),
)
_ACTION_PREFIX = re.compile(
    r"^(?:i\s+(?:want|would\s+like|need)|(?:can|could)\s+i\s+(?:get|have)|"
    r"(?:please\s+)?(?:choose|select|switch\s+to|start))\s+",
    re.IGNORECASE,
)

SelectionDisposition = Literal["retained", "open", "closed"]


def classify_service_selection(text: str | None) -> ServiceKind | None:
    """Return an explicit service-selection request, never a status question."""
    normalized = " ".join((text or "").casefold().split())
    if not normalized or _NEGATED_OR_INFORMATIONAL.search(normalized):
        return None
    matches = [service for service, pattern in _SERVICE_ALIASES if pattern.search(normalized)]
    if len(matches) != 1:
        return None
    bare_candidate = re.sub(r"\s+please[!. ]*$", "", normalized).rstrip(".! ")
    bare_alias = any(
        pattern.fullmatch(bare_candidate) for _, pattern in _SERVICE_ALIASES
    )
    request = _ACTION_PREFIX.match(normalized) is not None
    if bare_alias or request:
        return matches[0]
    return None


def retained_handoff_block(state: dict, tool_call_id: str) -> Command | None:
    """Return the one blocking response for retained specialist work."""
    if not SpecialistFlowView.from_state(state).owns_specialist_work:
        return None
    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    content=(
                        "New-service or paid-order change blocked because retained "
                        "specialist work is still active."
                    ),
                    tool_call_id=tool_call_id,
                ),
                AIMessage(retained_completion_first_message(state)),
            ]
        }
    )


def selection_disposition(
    *,
    state: dict,
    service: ServiceKind,
    accepts_new_order: Callable[[], bool],
) -> SelectionDisposition:
    """Evaluate the shared retained/open/closed service-selection policy."""
    if SpecialistFlowView.from_state(state).owns_specialist_work:
        return "retained"
    return "open" if accepts_new_order() else "closed"


async def route_tool_service_selection(
    *,
    service: ServiceKind,
    state: dict,
    tool_call_id: str,
    runtime: Any,
) -> Command:
    """Apply the same service-selection policy from a graph transfer tool."""
    context = runtime.context
    if selection_pending(state, context.restaurant_selection):
        return await selection_required_block(context, tool_call_id)
    disposition = selection_disposition(
        state=state,
        service=service,
        accepts_new_order=lambda: context.operational_lookups.accepts_new_order(
            service, context.recipient
        ),
    )
    if disposition == "retained":
        guard = retained_handoff_block(state, tool_call_id)
        assert guard is not None
        return guard

    if disposition == "closed":
        await send_new_order_closed_message(
            recipient=context.recipient,
            wa_client=context.wa_client,
            reply_to_message_id=state.get("reply_to_msg_id"),
        )
        return Command(
            graph=Command.PARENT,
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        f"{service.title()} handoff blocked because ordering is currently closed.",
                        tool_call_id=tool_call_id,
                    ),
                    AIMessage("/DoNotRespond: Ordering is currently closed."),
                ]
            },
        )

    if service == "delivery":
        transfer_message = ToolMessage(
            content=(
                "Transferred to delivery agent. Runtime has already approved new-order "
                "availability. Start the address flow immediately; do not ask for the date "
                "or time and do not reassess hours."
            ),
            tool_call_id=tool_call_id,
        )
        messages = [transfer_message]
        last_ai = next(
            (msg for msg in reversed(state.get("messages", ())) if isinstance(msg, AIMessage)),
            None,
        )
        if last_ai is not None:
            messages.insert(0, last_ai)
        return Command(
            graph=Command.PARENT,
            goto="delivery_agent",
            update={**new_specialist_flow_state("delivery"), "messages": messages},
        )

    result = await send_new_order_menu(
        recipient=context.recipient,
        state=state,
        rest_ref=resolve_menu_rest_ref(
            state, context.restaurant_selection, context.rest_ref
        ),
        wa_client=context.wa_client,
        logo_url=resolve_menu_logo_url(
            state, context.restaurant_selection, context.restaurant_logo_url
        ),
        operational_lookups=context.operational_lookups,
        thread_handler=context.thread_handler,
        order_type="takeaway",
        delivery_promo_caption=resolve_delivery_promo_caption(
            state, context.restaurant_selection, context.delivery_promo_caption
        ),
        takeaway_promo_caption=resolve_takeaway_promo_caption(
            state, context.restaurant_selection, context.takeaway_promo_caption
        ),
        reply_to_message_id=state.get("reply_to_msg_id"),
    )
    if result != "sent":
        return Command(
            graph=Command.PARENT,
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "New order menu blocked because the service is currently closed."
                        if result == "closed"
                        else "Failed to send restaurant menu.",
                        tool_call_id=tool_call_id,
                    )
                ]
            },
        )
    return Command(
        graph=Command.PARENT,
        goto=END,
        update={
            **new_specialist_flow_state("takeaway"),
            "messages": [
                ToolMessage(
                    "Restaurant menu sent to customer for takeaway order.",
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: The takeaway menu was successfully sent to the "
                    "customer. Wait for them to place the order. Do not send another menu "
                    "unless they explicitly request one and no retained order is active."
                ),
            ],
        },
    )


async def route_service_selection(
    *,
    recipient: str,
    service: ServiceKind,
    human_msg: str,
    graph_adapter: GraphAdapter,
    runtime: RestaurantRuntime,
    rest_ref: str | None = None,
) -> None:
    """Apply one retained/open/closed selection policy for every adapter."""
    try:
        current_state = await graph_adapter.debug_state_values(recipient=recipient)
    except Exception:
        logger.exception(
            "Could not inspect service-selection state for recipient {}; preserving ownership",
            recipient,
        )
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient, msgs=[HumanMessage(human_msg)]
        )
        return

    selection = runtime.presentation.restaurant_selection
    if selection_pending(current_state, selection):
        await select_restaurant_wa_send(
            recipient=recipient,
            wa_client=runtime.async_wa_client,
            selection=selection,
        )
        return

    disposition = selection_disposition(
        state=current_state,
        service=service,
        accepts_new_order=lambda: runtime.operational_lookups.accepts_new_order(
            service, recipient
        ),
    )
    if disposition == "retained":
        reply = retained_completion_first_message(current_state)
        try:
            await graph_adapter.run_rest_graph_with_custom_msg(
                recipient=recipient,
                msgs=[HumanMessage(human_msg), AIMessage(reply)],
                persist_only=True,
            )
        except Exception:
            # The retained checkpoint has already been safely read above. Do
            # not replace the warm customer response with a second model turn
            # merely because writing conversation history failed.
            logger.exception(
                "Could not persist retained handoff reply for recipient {}", recipient
            )
        await runtime.async_wa_client.send_message(to=recipient, text=reply)
        return

    if disposition == "closed":
        await send_new_order_closed_message(
            recipient=recipient, wa_client=runtime.async_wa_client
        )
        return

    state_update = new_specialist_flow_state(service, rest_ref=rest_ref)
    if service == "delivery":
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            msgs=[
                HumanMessage(human_msg),
                SystemMessage(
                    "Runtime has approved new delivery ordering. Do not ask for the "
                    "date or time and do not reassess hours. Start the address flow immediately."
                ),
            ],
            state_update_dict=state_update,
        )
        return

    pool = await runtime.settings.database.get_pool()
    config, _ = await get_config_for_recipient(
        recipient, pool, agent=runtime.identity.rest_ref
    )
    await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        pool=pool,
        config=config,
        msgs=[HumanMessage(human_msg)],
        state_update_dict=state_update,
        persist_only=True,
    )
    result = await send_new_order_menu(
        recipient=recipient,
        state=state_update,
        # `current_state` (not `state_update`) carries the persisted
        # `selected_rest_ref`; `new_specialist_flow_state` never sets it.
        rest_ref=resolve_menu_rest_ref(
            current_state, selection, runtime.identity.rest_ref
        ),
        wa_client=runtime.async_wa_client,
        logo_url=resolve_menu_logo_url(
            current_state, selection, runtime.presentation.logo_url or ""
        ),
        operational_lookups=runtime.operational_lookups,
        thread_handler=ThreadHandler(pool, agent=runtime.identity.rest_ref),
        order_type="takeaway",
        delivery_promo_caption=resolve_delivery_promo_caption(
            current_state, selection, runtime.presentation.delivery_promo_caption
        ),
        takeaway_promo_caption=resolve_takeaway_promo_caption(
            current_state, selection, runtime.presentation.takeaway_promo_caption
        ),
    )
    marker = {
        "sent": (
            "/DoNotRespond: The takeaway menu was successfully sent to the customer. "
            "Wait for them to place the order. Do not send another menu unless they "
            "explicitly request one and no retained order is active."
        ),
        "closed": "/DoNotRespond: Takeaway ordering is currently closed. No menu was sent.",
        "failed": (
            "/DoNotRespond: The takeaway menu could not be sent. The customer was asked "
            "to try again later."
        ),
    }[result]
    try:
        await graph_adapter.run_rest_graph_with_custom_msg(
            recipient=recipient,
            pool=pool,
            config=config,
            msgs=[AIMessage(marker)],
            persist_only=True,
        )
    except Exception:
        # The customer-facing send has already succeeded or failed above. Do not
        # retry it merely because its transcript record could not be persisted.
        logger.exception(
            "Could not persist deterministic takeaway menu outcome for recipient {}",
            recipient,
        )
