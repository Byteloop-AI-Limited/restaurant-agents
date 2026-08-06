import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from langchain_core.messages import SystemMessage

from restaurant_agent_runtime import EnquiryMenu, EnquiryOption
from restaurant_agent_runtime.rest_agent.agent_wa_senders import (
    CallbackButtonData,
    select_enquiry_wa_send,
)
from restaurant_agent_runtime.watomation import on_callback_handler


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
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
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
    )
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


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
async def test_enquiry_sender_uses_the_app_owned_menu():
    wa_client = AsyncMock()
    sfcs_menu = EnquiryMenu(
        prompt="How can we help?",
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
    assert [button.title for button in kwargs["buttons"]] == [
        "Share feedback",
        "Subscribe for offers",
    ]
    assert all('"action":"/SelectEnquiry"' in button.callback_data for button in kwargs["buttons"])


def test_enquiry_menu_rejects_more_than_whatsapp_allows():
    with pytest.raises(ValueError, match="between one and three"):
        EnquiryMenu(
            prompt="What would you like help with?",
            options=tuple(
                EnquiryOption(f"Option {number}", f"I choose option {number}")
                for number in range(4)
            ),
        )


class FakeOperationalLookups:
    """Minimal double mirroring OperationalLookupCache.accepts_new_order."""

    def __init__(self, *, delivery_open=True, takeaway_open=True, overwatch_recipients=()):
        self.delivery_open = delivery_open
        self.takeaway_open = takeaway_open
        self.overwatch_recipients = set(overwatch_recipients)

    def accepts_new_order(self, order_type, recipient):
        if recipient in self.overwatch_recipients:
            return True
        return self.delivery_open if order_type == "delivery" else self.takeaway_open


@pytest.mark.asyncio
async def test_closed_service_resend_passes_operational_lookups_to_the_sender():
    """The order-cutoff resend must let an Overwatch recipient through too."""
    ops = FakeOperationalLookups(delivery_open=False)
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        operational_lookups=ops,
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

    select_service_sender.assert_awaited_once_with(
        recipient="447000000001",
        wa_client=wa,
        rest_ref="bnat",
        operational_lookups=ops,
    )
    graph_adapter.run_rest_graph_with_custom_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_active_agent_resend_passes_operational_lookups_to_the_sender():
    """This resend used to fail open with no availability information at all."""
    ops = FakeOperationalLookups(delivery_open=False, takeaway_open=False)
    graph_adapter = SimpleNamespace(run_rest_graph_with_custom_msg=AsyncMock())
    runtime = SimpleNamespace(
        identity=SimpleNamespace(rest_ref="BNAT"),
        operational_lookups=ops,
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
