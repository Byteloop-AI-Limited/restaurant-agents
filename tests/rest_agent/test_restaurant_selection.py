"""Unit tests for the restaurant-selection projection and its three gates.

`selected_rest_ref` is the customer's choice among multiple restaurant
brands behind one app; `rest_ref` is the invariant app identity, always
seeded on a new thread. These tests pin the single-writer invariant (never
fall back to `rest_ref`) and exercise the resolvers through the same
`debug_state_values` projection the real callback/typed-message path uses,
not a hand-built full-state dict.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END

from restaurant_agent_runtime.rest_agent.agents.multi_agent import route_after_agent
from restaurant_agent_runtime.rest_agent.restaurant_selection import (
    dinein_available,
    resolve_menu_logo_url,
    resolve_menu_rest_ref,
    selected_choice,
    selection_pending,
    selection_required_block,
)
from restaurant_agent_runtime.rest_agent.service_selection import (
    route_service_selection,
    route_tool_service_selection,
)
from restaurant_agent_runtime.rest_agent.state_debug import get_state_values
from restaurant_agent_runtime.runtime import RestaurantChoice, RestaurantSelection

ELAI = RestaurantChoice("ELAS", "Elai", "Elai", "I want to order from Elai")
WINGS = RestaurantChoice(
    "CHKS",
    "Wings and Things",
    "Wings and Things",
    "I want to order from Wings and Things",
    supports_dine_in=False,
)
SELECTION = RestaurantSelection(prompt="Which restaurant?", choices=(ELAI, WINGS))


def test_selection_is_inert_when_not_configured():
    state = {"rest_ref": "sfcs", "selected_rest_ref": None}
    assert selected_choice(state, None) is None
    assert selection_pending(state, None) is False
    assert resolve_menu_rest_ref(state, None, "sfcs") == "sfcs"
    assert resolve_menu_logo_url(state, None, "logo") == "logo"
    assert dinein_available(state, None, "https://reserve.example") is True
    assert dinein_available(state, None, None) is False


def test_selection_pending_true_until_selected_rest_ref_is_set():
    assert selection_pending({}, SELECTION) is True
    assert selection_pending({"selected_rest_ref": None}, SELECTION) is True
    assert selection_pending({"selected_rest_ref": "chks"}, SELECTION) is False


def test_selected_choice_never_falls_back_to_rest_ref():
    """Regression: rest_ref is always seeded on a new thread (agent_runner.py),
    so treating it as a stand-in for the customer's choice would make the
    selection gate never fire for a fresh ELAS thread."""
    state = {"rest_ref": "elas", "selected_rest_ref": None}
    assert selected_choice(state, SELECTION) is None
    assert selection_pending(state, SELECTION) is True


def test_selected_choice_resolves_case_insensitively():
    assert selected_choice({"selected_rest_ref": "chks"}, SELECTION) == WINGS
    assert selected_choice({"selected_rest_ref": "CHKS"}, SELECTION) == WINGS
    assert selected_choice({"selected_rest_ref": "unknown"}, SELECTION) is None


def test_resolve_menu_rest_ref_and_logo_use_the_selected_choice():
    state = {"selected_rest_ref": "chks"}
    assert resolve_menu_rest_ref(state, SELECTION, "elas") == "CHKS"
    assert resolve_menu_logo_url(state, SELECTION, "fallback-logo") == "fallback-logo"

    elai_with_logo = RestaurantChoice(
        "ELAS", "Elai", "Elai", "hi", logo_url="https://logo/elai.png"
    )
    selection_with_logo = RestaurantSelection(
        prompt="p", choices=(elai_with_logo, WINGS)
    )
    assert (
        resolve_menu_logo_url({"selected_rest_ref": "elas"}, selection_with_logo, "x")
        == "https://logo/elai.png"
    )


def test_dinein_available_respects_per_choice_flag_and_reservation_url():
    assert dinein_available(
        {"selected_rest_ref": "elas"}, SELECTION, "https://reserve.example"
    ) is True
    assert dinein_available(
        {"selected_rest_ref": "chks"}, SELECTION, "https://reserve.example"
    ) is False
    assert dinein_available({"selected_rest_ref": "elas"}, SELECTION, None) is False


@pytest.mark.asyncio
async def test_selection_required_block_sends_buttons_and_ends_the_turn(monkeypatch):
    """Sends the restaurant-selection buttons directly and ends the current
    node's own turn (no Command.PARENT, no trailing SystemMessage) so the
    checkpointed tool-call/tool-response pair stays adjacent — see the
    docstring on `selection_required_block` for why the previous
    parent-graph-redirect shape corrupted the message tail."""
    sent = {}

    async def fake_select_restaurant_wa_send(*, recipient, wa_client, selection):
        sent["recipient"] = recipient
        sent["selection"] = selection

    monkeypatch.setattr(
        "restaurant_agent_runtime.rest_agent.agent_wa_senders.select_restaurant_wa_send",
        fake_select_restaurant_wa_send,
    )
    ctx = SimpleNamespace(
        recipient="447000000001", wa_client=object(), restaurant_selection=SELECTION
    )

    command = await selection_required_block(ctx, "tc-1")

    assert sent == {"recipient": "447000000001", "selection": SELECTION}
    assert command.goto == END
    assert command.graph is None
    assert command.update["messages"][0].tool_call_id == "tc-1"
    assert "no restaurant has been selected" in command.update["messages"][0].content
    assert "/DoNotRespond:" in command.update["messages"][1].content
    assert (
        route_after_agent(
            {"messages": command.update["messages"], "active_agent": "triage_agent"}
        )
        == "__end__"
    )


@pytest.mark.asyncio
async def test_transfer_to_dinein_declines_a_typed_request_for_a_brand_that_excludes_it():
    """CHKS (Wings and Things) no longer shows "Book a table" in the enquiry
    menu (ADR-0024, EnquiryOption.only_for_rest_refs), so this guard is now
    only a typed-intent backstop — a CHKS customer who types "book a table"
    instead of tapping a menu row. It must respond with a plain string, not a
    Command: LangChain's tool node wraps a returned string into a ToolMessage
    and assigns the originating call's tool_call_id itself, which is what
    keeps the checkpointed tail correctly paired without a Command.PARENT
    redirect."""
    from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
        transfer_to_dinein,
    )

    state = {"selected_rest_ref": "CHKS"}
    runtime = SimpleNamespace(
        state=state,
        tool_call_id="tc-1",
        context=SimpleNamespace(
            restaurant_selection=SELECTION,
            reservation_base_url="https://elai-reservation.byteloop.ai",
        ),
    )

    result = await transfer_to_dinein(runtime)

    assert isinstance(result, str)
    assert "does not offer dine-in" in result


@pytest.mark.asyncio
async def test_transfer_to_dinein_succeeds_for_a_brand_that_supports_it():
    from restaurant_agent_runtime.rest_agent.agents.agent_harness import (
        transfer_to_dinein,
    )

    state = {"selected_rest_ref": "ELAS", "retain_thread": False, "messages": []}
    runtime = SimpleNamespace(
        state=state,
        tool_call_id="tc-1",
        context=SimpleNamespace(
            recipient="447000000001",
            restaurant_selection=SELECTION,
            reservation_base_url="https://elai-reservation.byteloop.ai",
        ),
    )

    command = await transfer_to_dinein(runtime)

    assert command.goto == "dinein_agent"
    assert command.update["active_agent"] == "dinein_agent"


class FakeOperationalLookups:
    def accepts_new_order(self, *_args, **_kwargs):
        return True


@pytest.mark.asyncio
async def test_route_tool_service_selection_blocks_pending_selection(monkeypatch):
    sent = {}

    async def fake_select_restaurant_wa_send(*, recipient, wa_client, selection):
        sent["recipient"] = recipient

    monkeypatch.setattr(
        "restaurant_agent_runtime.rest_agent.agent_wa_senders.select_restaurant_wa_send",
        fake_select_restaurant_wa_send,
    )
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            recipient="447000000001",
            wa_client=object(),
            restaurant_selection=SELECTION,
            operational_lookups=FakeOperationalLookups(),
        )
    )
    command = await route_tool_service_selection(
        service="delivery",
        state={"selected_rest_ref": None},
        tool_call_id="tc-1",
        runtime=runtime,
    )
    assert sent == {"recipient": "447000000001"}
    assert command.goto == END
    assert command.graph is None


@pytest.mark.asyncio
async def test_route_service_selection_sends_restaurant_buttons_through_the_real_projection(
    monkeypatch,
):
    """Drives the gate through debug_state_values's actual pass-through
    projection (get_state_values), not a hand-built dict, so a regression
    that turns the projection into a key whitelist would be caught here."""
    full_state = {
        "rest_ref": "elas",
        "selected_rest_ref": None,
        "active_agent": "triage_agent",
        "messages": [HumanMessage("hi")],
        "retain_thread": False,
    }
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=get_state_values(full_state)),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    sent = {}

    async def fake_select_restaurant_wa_send(*, recipient, wa_client, selection):
        sent["recipient"] = recipient
        sent["selection"] = selection

    monkeypatch.setattr(
        "restaurant_agent_runtime.rest_agent.service_selection.select_restaurant_wa_send",
        fake_select_restaurant_wa_send,
    )
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(restaurant_selection=SELECTION),
        async_wa_client=object(),
    )

    await route_service_selection(
        recipient="447000000001",
        service="delivery",
        human_msg="I want delivery",
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    assert sent == {"recipient": "447000000001", "selection": SELECTION}
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_service_selection_proceeds_once_selected():
    full_state = {
        "rest_ref": "elas",
        "selected_rest_ref": "chks",
        "active_agent": "triage_agent",
        "messages": [],
        "retain_thread": False,
    }
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value=get_state_values(full_state)),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        presentation=SimpleNamespace(restaurant_selection=SELECTION),
        operational_lookups=FakeOperationalLookups(),
        async_wa_client=object(),
    )

    await route_service_selection(
        recipient="447000000001",
        service="delivery",
        human_msg="I want delivery",
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once()
