import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pywa.types import SectionList

from restaurant_agent_runtime import EnquiryMenu, EnquiryOption
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    CallbackButtonData,
    select_enquiry_wa_send,
)
from restaurant_agent_runtime.watomation import on_callback_handler
from restaurant_agent_runtime.rest_agent import service_selection


def _callback(*, callback_id: str, data: dict):
    return SimpleNamespace(
        id=callback_id,
        data=json.dumps(data),
        from_user=SimpleNamespace(wa_id="447000000001"),
    )


BNAT_ENQUIRY_MENU = EnquiryMenu(
    prompt="What would you like help with?",
    options=(
        EnquiryOption("Share feedback", "I want to share feedback"),
        EnquiryOption("Parking availability", "I want to know about parking availability"),
        EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
    ),
)


@pytest.mark.asyncio
async def test_enquiry_service_callback_bypasses_stale_fulfilment_agent(monkeypatch):
    enquiry_sender = AsyncMock()
    monkeypatch.setattr(
        on_callback_handler,
        "select_enquiry_wa_send",
        enquiry_sender,
    )
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"selected_rest_ref": None}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        settings=SimpleNamespace(database_client=object()),
        presentation=SimpleNamespace(enquiry_menu=BNAT_ENQUIRY_MENU),
    )
    callback = _callback(
        callback_id="stale-enquiry-service",
        data={
            "action": "/SelectService",
            "rest_ref": "bnat",
            "active_agent": "takeaway_agent",
            "human_msg": "I have an enquiry",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    enquiry_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=ANY,
        rest_ref="bnat",
        menu=BNAT_ENQUIRY_MENU,
        selected_rest_ref=None,
    )
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_enquiry_service_callback_hides_brand_restricted_rows_for_chks(monkeypatch):
    """The primary "More options" render path (/SelectService, not the LLM
    tool) must resolve the customer's chosen brand and hide restricted rows
    accordingly — this is the path that broke in production (ADR-0024)."""
    elas_menu = EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            *BNAT_ENQUIRY_MENU.options,
            EnquiryOption(
                "Book a table", "I want to book a table", only_for_rest_refs=("ELAS",)
            ),
        ),
    )
    enquiry_sender = AsyncMock()
    monkeypatch.setattr(on_callback_handler, "select_enquiry_wa_send", enquiry_sender)
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"selected_rest_ref": "CHKS"}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="ELAS"),
        settings=SimpleNamespace(database_client=object()),
        presentation=SimpleNamespace(enquiry_menu=elas_menu),
    )
    callback = _callback(
        callback_id="chks-enquiry-service",
        data={
            "action": "/SelectService",
            "rest_ref": "elas",
            "active_agent": "triage_agent",
            "human_msg": "I have an enquiry",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    enquiry_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=ANY,
        rest_ref="elas",
        menu=elas_menu,
        selected_rest_ref="CHKS",
    )


@pytest.mark.asyncio
async def test_enquiry_service_callback_shows_brand_restricted_rows_for_elas(monkeypatch):
    elas_menu = EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            *BNAT_ENQUIRY_MENU.options,
            EnquiryOption(
                "Book a table", "I want to book a table", only_for_rest_refs=("ELAS",)
            ),
        ),
    )
    enquiry_sender = AsyncMock()
    monkeypatch.setattr(on_callback_handler, "select_enquiry_wa_send", enquiry_sender)
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"selected_rest_ref": "ELAS"}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="ELAS"),
        settings=SimpleNamespace(database_client=object()),
        presentation=SimpleNamespace(enquiry_menu=elas_menu),
    )
    callback = _callback(
        callback_id="elas-enquiry-service",
        data={
            "action": "/SelectService",
            "rest_ref": "elas",
            "active_agent": "triage_agent",
            "human_msg": "I have an enquiry",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    enquiry_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=ANY,
        rest_ref="elas",
        menu=elas_menu,
        selected_rest_ref="ELAS",
    )


@pytest.mark.asyncio
async def test_enquiry_service_callback_degrades_to_unrestricted_rows_on_a_failed_read(
    monkeypatch,
):
    enquiry_sender = AsyncMock()
    monkeypatch.setattr(on_callback_handler, "select_enquiry_wa_send", enquiry_sender)
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(side_effect=RuntimeError("db unavailable")),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        settings=SimpleNamespace(database_client=object()),
        presentation=SimpleNamespace(enquiry_menu=BNAT_ENQUIRY_MENU),
    )
    callback = _callback(
        callback_id="failed-state-read-enquiry-service",
        data={
            "action": "/SelectService",
            "rest_ref": "bnat",
            "active_agent": "takeaway_agent",
            "human_msg": "I have an enquiry",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    enquiry_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=ANY,
        rest_ref="bnat",
        menu=BNAT_ENQUIRY_MENU,
        selected_rest_ref=None,
    )


@pytest.mark.asyncio
async def test_specific_enquiry_callback_runs_triage_directly():
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(identity=SimpleNamespace(rest_ref="BNAT"))
    callback = _callback(
        callback_id="specific-enquiry-option",
        data={
            "action": "/SelectEnquiry",
            "rest_ref": "bnat",
            "active_agent": "takeaway_agent",
            "human_msg": "I want to share feedback",
        },
    )

    await on_callback_handler.select_enquiry_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once()
    kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert kwargs["recipient"] == "447000000001"
    assert kwargs["state_update_dict"] == {
        "rest_ref": "bnat",
        "active_agent": "triage_agent",
    }
    assert kwargs["msgs"][0].content == "I want to share feedback"
    assert isinstance(kwargs["msgs"][-1], SystemMessage)


@pytest.mark.asyncio
async def test_enquiry_selection_handler_accepts_a_list_reply():
    """A SectionList row tap arrives as CallbackSelection, not CallbackButton.

    select_enquiry_handler's `callback` parameter is untyped and only reads
    `.from_user`/`.data`, both of which CallbackSelection has — this proves
    the same handler function works for a list reply.
    """
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(identity=SimpleNamespace(rest_ref="ELAS"))
    payload = json.dumps(
        {
            "action": "/SelectEnquiry",
            "rest_ref": "elas",
            "active_agent": "triage_agent",
            "human_msg": "I want to book a table",
        }
    )
    callback_selection = SimpleNamespace(
        id="list-reply-1",
        data=payload,
        title="Book a table",
        description=None,
        from_user=SimpleNamespace(wa_id="447000000001"),
    )

    await on_callback_handler.select_enquiry_handler(
        SimpleNamespace(),
        callback_selection,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once()
    kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert kwargs["msgs"][0].content == "I want to book a table"
    assert kwargs["state_update_dict"] == {"rest_ref": "elas", "active_agent": "triage_agent"}


@pytest.mark.asyncio
async def test_enquiry_sender_uses_the_app_owned_menu():
    wa_client = AsyncMock()
    sfcs_menu = EnquiryMenu(
        prompt="How can we help?",
        button_title="Choose an option",
        options=(
            EnquiryOption("Share feedback", "I want to share feedback"),
            EnquiryOption("Subscribe for offers", "I want to subscribe for offers"),
        ),
    )

    await select_enquiry_wa_send(
        recipient="447000000001",
        wa_client=wa_client,
        rest_ref="sfcs",
        menu=sfcs_menu,
    )

    kwargs = wa_client.send_message.await_args.kwargs
    assert kwargs["text"] == "How can we help?"
    section_list = kwargs["buttons"]
    assert isinstance(section_list, SectionList)
    assert section_list.button_title == "Choose an option"
    sections = list(section_list.sections)
    assert len(sections) == 1
    rows = list(sections[0].rows)
    assert [row.title for row in rows] == ["Share feedback", "Subscribe for offers"]
    assert all('"action":"/SelectEnquiry"' in row.callback_data for row in rows)


@pytest.mark.asyncio
async def test_enquiry_rows_carry_optional_description():
    wa_client = AsyncMock()
    menu = EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            EnquiryOption(
                "Book a table",
                "I want to book a table",
                description="Reserve a table at Elai",
            ),
        ),
    )

    await select_enquiry_wa_send(
        recipient="447000000001", wa_client=wa_client, rest_ref="elas", menu=menu
    )

    section_list = wa_client.send_message.await_args.kwargs["buttons"]
    rows = list(list(section_list.sections)[0].rows)
    assert rows[0].description == "Reserve a table at Elai"


def test_enquiry_menu_rejects_more_than_whatsapp_allows():
    with pytest.raises(ValueError, match="between one and ten"):
        EnquiryMenu(
            prompt="What would you like help with?",
            options=tuple(
                EnquiryOption(f"Option {number}", f"I choose option {number}")
                for number in range(11)
            ),
        )


def test_enquiry_menu_accepts_up_to_ten_options():
    menu = EnquiryMenu(
        prompt="What would you like help with?",
        options=tuple(
            EnquiryOption(f"Option {number}", f"I choose option {number}")
            for number in range(10)
        ),
    )
    assert len(menu.options) == 10


def test_enquiry_option_title_cap_is_twenty_four():
    EnquiryOption("A" * 24, "human message")
    with pytest.raises(ValueError, match="at most 24 characters"):
        EnquiryOption("A" * 25, "human message")


def test_enquiry_option_rejects_human_message_over_callback_budget():
    EnquiryOption("Title", "A" * 100)
    with pytest.raises(ValueError, match="at most 100 characters"):
        EnquiryOption("Title", "A" * 101)


def test_enquiry_option_is_visible_for_unrestricted_by_default():
    option = EnquiryOption("Share feedback", "I want to share feedback")
    assert option.is_visible_for("ELAS") is True
    assert option.is_visible_for("CHKS") is True
    assert option.is_visible_for(None) is True


def test_enquiry_option_is_visible_for_respects_restriction():
    option = EnquiryOption(
        "Book a table", "I want to book a table", only_for_rest_refs=("ELAS",)
    )
    assert option.is_visible_for("ELAS") is True
    assert option.is_visible_for("elas") is True
    assert option.is_visible_for(" elas ") is True
    assert option.is_visible_for("CHKS") is False
    assert option.is_visible_for(None) is False


def test_enquiry_option_rejects_empty_only_for_rest_refs():
    with pytest.raises(ValueError, match="empty tuple"):
        EnquiryOption("Book a table", "I want to book a table", only_for_rest_refs=())


def test_enquiry_option_normalizes_only_for_rest_refs_to_stripped_uppercase():
    option = EnquiryOption("Title", "human message", only_for_rest_refs=(" chks ",))
    assert option.only_for_rest_refs == ("CHKS",)


def test_enquiry_menu_visible_options_for_filters_restricted_rows():
    menu = EnquiryMenu(
        prompt="What would you like help with?",
        options=(
            EnquiryOption("Share feedback", "I want to share feedback"),
            EnquiryOption(
                "Book a table", "I want to book a table", only_for_rest_refs=("ELAS",)
            ),
        ),
    )
    assert [o.title for o in menu.visible_options_for("CHKS")] == ["Share feedback"]
    assert [o.title for o in menu.visible_options_for("ELAS")] == [
        "Share feedback",
        "Book a table",
    ]
    assert [o.title for o in menu.visible_options_for(None)] == ["Share feedback"]


def test_enquiry_menu_rejects_a_menu_with_no_always_visible_option():
    with pytest.raises(ValueError, match="at least one option visible to every brand"):
        EnquiryMenu(
            prompt="What would you like help with?",
            options=(
                EnquiryOption(
                    "Book a table", "I want to book a table", only_for_rest_refs=("ELAS",)
                ),
            ),
        )


class FakeOperationalLookups:
    """Minimal double mirroring OperationalLookupCache.accepts_new_order."""

    def __init__(self, *, delivery_open=True, takeaway_open=True, overwatch_recipients=()):
        self.delivery_open = delivery_open
        self.takeaway_open = takeaway_open
        self.overwatch_recipients = set(overwatch_recipients)

    def accepts_new_order(self, order_type, recipient, at=None):
        if recipient in self.overwatch_recipients:
            return True
        return self.delivery_open if order_type == "delivery" else self.takeaway_open

@pytest.mark.asyncio
async def test_closed_service_sends_only_the_deterministic_closed_message():
    ops = FakeOperationalLookups(delivery_open=False)
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"retain_thread": False}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        operational_lookups=ops,
        async_wa_client=SimpleNamespace(send_message=AsyncMock()),
        presentation=SimpleNamespace(restaurant_selection=None),
    )
    select_service_sender = AsyncMock()
    callback = _callback(
        callback_id="closed-service",
        data={
            "action": "/SelectService",
            "rest_ref": "bnat",
            "active_agent": "delivery_agent",
            "human_msg": "I want delivery",
        },
    )
    wa = SimpleNamespace(send_message=AsyncMock())

    await on_callback_handler.select_service_handler(
        wa,
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=select_service_sender,
    )

    runtime.async_wa_client.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Ordering is currently closed.",
        reply_to_message_id=None,
    )
    select_service_sender.assert_not_awaited()
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_takeaway_callback_persists_and_sends_menu_without_model(monkeypatch):
    ops = FakeOperationalLookups(takeaway_open=True)
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(return_value={"retain_thread": False}),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    pool = object()
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="SFCS"),
        operational_lookups=ops,
        async_wa_client=SimpleNamespace(),
        settings=SimpleNamespace(database=SimpleNamespace(get_pool=AsyncMock(return_value=pool))),
        presentation=SimpleNamespace(
            logo_url="logo",
            restaurant_selection=None,
            delivery_promo_caption="20% off delivery",
            takeaway_promo_caption="Get started with your collection order",
        ),
    )
    monkeypatch.setattr(
        service_selection,
        "get_config_for_recipient",
        AsyncMock(return_value=({"configurable": {"thread_id": "thread-1"}}, False)),
    )
    menu_sender = AsyncMock(return_value="sent")
    monkeypatch.setattr(service_selection, "send_new_order_menu", menu_sender)

    callback = _callback(
        callback_id="takeaway-direct",
        data={
            "action": "/SelectService",
            "rest_ref": "sfcs",
            "active_agent": "takeaway_agent",
            "human_msg": "I want takeaway",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    assert graph_adapter.run_rest_graph_with_custom_msg.await_count == 2
    first = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[0].kwargs
    assert first["persist_only"] is True
    assert first["state_update_dict"]["active_agent"] == "takeaway_agent"
    assert isinstance(first["msgs"][0], HumanMessage)
    second = graph_adapter.run_rest_graph_with_custom_msg.await_args_list[1].kwargs
    assert second["persist_only"] is True
    assert "The takeaway menu was successfully sent" in second["msgs"][0].content
    menu_sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_retained_service_callback_keeps_the_current_specialist():
    graph_adapter = SimpleNamespace(
        debug_state_values=AsyncMock(
            return_value={
                "active_agent": "delivery_agent",
                "retain_thread": True,
            }
        ),
        run_rest_graph_with_custom_msg=AsyncMock(),
    )
    wa_client = SimpleNamespace(send_message=AsyncMock())
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="SFCS"),
        async_wa_client=wa_client,
        presentation=SimpleNamespace(restaurant_selection=None),
    )
    callback = _callback(
        callback_id="retained-delivery-service-selection",
        data={
            "action": "/SelectService",
            "rest_ref": "sfcs",
            "active_agent": "takeaway_agent",
            "human_msg": "I want takeaway",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    graph_adapter.debug_state_values.assert_awaited_once_with(recipient="447000000001")
    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once()
    kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert kwargs["recipient"] == "447000000001"
    assert kwargs["msgs"][0] == HumanMessage("I want takeaway")
    assert "current delivery order first" in kwargs["msgs"][1].content
    assert kwargs["persist_only"] is True
    wa_client.send_message.assert_awaited_once_with(
        to="447000000001", text=kwargs["msgs"][1].content
    )


@pytest.mark.asyncio
async def test_no_active_agent_resend_passes_operational_lookups_to_the_sender():
    """This resend used to fail open with no availability information at all."""
    ops = FakeOperationalLookups(delivery_open=False, takeaway_open=False)
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        operational_lookups=ops,
        presentation=SimpleNamespace(
            restaurant_selection=None,
            delivery_button_label="Delivery (10%)",
            takeaway_button_label="Collection",
            enquiry_button_label="More Options",
        ),
    )
    select_service_sender = AsyncMock()
    callback = _callback(
        callback_id="no-active-agent",
        data={
            "action": "/SelectService",
            "rest_ref": "bnat",
            "human_msg": "hi",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=select_service_sender,
    )

    select_service_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=ANY,
        rest_ref="bnat",
        operational_lookups=ops,
        delivery_button_label="Delivery (10%)",
        takeaway_button_label="Collection",
        enquiry_button_label="More Options",
    )
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_specific_enquiry_callback_runs_triage_directly():
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(identity=SimpleNamespace(rest_ref="BNAT"))
    callback = _callback(
        callback_id="legacy-specific-enquiry-option",
        data={
            "action": "/SelectService",
            "rest_ref": "bnat",
            "active_agent": "takeaway_agent",
            "human_msg": "I want to share feedback",
        },
    )

    await on_callback_handler.select_service_handler(
        SimpleNamespace(),
        callback,
        callback_data_type=CallbackButtonData,
        graph_adapter=graph_adapter,
        runtime=runtime,
        select_service_sender=AsyncMock(),
    )

    graph_adapter.run_rest_graph_with_custom_msg.assert_awaited_once()
    kwargs = graph_adapter.run_rest_graph_with_custom_msg.await_args.kwargs
    assert kwargs["state_update_dict"]["active_agent"] == "triage_agent"
    assert kwargs["msgs"][0].content == "I want to share feedback"
    assert isinstance(kwargs["msgs"][-1], SystemMessage)
