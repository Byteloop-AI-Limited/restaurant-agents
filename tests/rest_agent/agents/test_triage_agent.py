"""Unit tests for ordered triage replies, feedback acknowledgement, and menus."""

from types import SimpleNamespace
from unittest.mock import ANY

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END

from restaurant_agent_runtime.rest_agent.agents import triage


def _runtime(*, events: list[tuple[str, dict]], contact_phone: str | None = None):
    async def send_message(**kwargs):
        events.append(("message", kwargs))

    return SimpleNamespace(
        context=SimpleNamespace(
            recipient="447000000001",
            rest_ref="SFCS",
            wa_client=SimpleNamespace(send_message=send_message),
            operational_lookups=object(),
            delivery_button_label="Delivery",
            takeaway_button_label="Collection",
            enquiry_button_label="More options",
            restaurant_contact_phone=contact_phone,
            client_ordelo=object(),
            restaurant_selection=None,
        )
    )


@pytest.mark.asyncio
async def test_service_selection_sends_answer_before_buttons_and_ends_turn(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def send_service_selection(**kwargs):
        events.append(("service_selection", kwargs))

    monkeypatch.setattr(triage, "select_service_wa_send", send_service_selection)
    command = await triage.ask_user_to_select_service.coroutine(
        state={"rest_ref": "sfcs"},
        tool_call_id="tool-1",
        runtime=_runtime(events=events),
        message_before_selection="For halal options, choose Delivery or Collection and the team can assist.",
    )

    assert events == [
        (
            "message",
            {
                "to": "447000000001",
                "text": "For halal options, choose Delivery or Collection and the team can assist.",
            },
        ),
        (
            "service_selection",
            {
                "recipient": "447000000001",
                "wa_client": ANY,
                "rest_ref": "sfcs",
                "operational_lookups": ANY,
                "delivery_button_label": "Delivery",
                "takeaway_button_label": "Collection",
                "enquiry_button_label": "More options",
            },
        ),
    ]
    assert command.goto == END
    assert isinstance(command.update["messages"][-1], AIMessage)
    assert "/DoNotRespond:" in command.update["messages"][-1].content


@pytest.mark.asyncio
async def test_service_selection_keeps_bare_menu_compatibility(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def send_service_selection(**kwargs):
        events.append(("service_selection", kwargs))

    monkeypatch.setattr(triage, "select_service_wa_send", send_service_selection)
    await triage.ask_user_to_select_service.coroutine(
        state={"rest_ref": "sfcs"},
        tool_call_id="tool-1",
        runtime=_runtime(events=events),
    )

    assert [event[0] for event in events] == ["service_selection"]


@pytest.mark.asyncio
async def test_feedback_success_sends_model_acknowledgement_before_buttons(monkeypatch):
    events: list[tuple[str, dict]] = []
    submitted = []

    class FakeOrdeloService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def submit_restaurant_feedback(self, request):
            submitted.append(request)
            return {"status": "scheduled"}

    async def send_service_selection(**kwargs):
        events.append(("service_selection", kwargs))

    monkeypatch.setattr(triage, "OrdeloService", FakeOrdeloService)
    monkeypatch.setattr(triage, "select_service_wa_send", send_service_selection)
    acknowledgement = (
        "Thank you for your kind feedback — we really appreciate it. "
        "I've passed it to the restaurant team."
    )

    command = await triage.submit_restaurant_feedback.coroutine(
        description="The whole WhatsApp solution is very neat, thank you.",
        order_reference=None,
        acknowledgement_message=acknowledgement,
        state={"rest_ref": "sfcs", "wa_name": "Lohith"},
        tool_call_id="tool-2",
        runtime=_runtime(events=events),
    )

    assert submitted[0].description == "The whole WhatsApp solution is very neat, thank you."
    assert submitted[0].order_reference is None
    assert events[0] == (
        "message",
        {"to": "447000000001", "text": acknowledgement},
    )
    assert events[1][0] == "service_selection"
    assert command.goto == END
    assert "/DoNotRespond:" in command.update["messages"][-1].content


@pytest.mark.asyncio
async def test_feedback_failure_does_not_send_success_acknowledgement(monkeypatch):
    events: list[tuple[str, dict]] = []

    class FakeOrdeloService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def submit_restaurant_feedback(self, request):
            return None

    async def send_service_selection(**kwargs):
        events.append(("service_selection", kwargs))

    monkeypatch.setattr(triage, "OrdeloService", FakeOrdeloService)
    monkeypatch.setattr(triage, "select_service_wa_send", send_service_selection)
    command = await triage.submit_restaurant_feedback.coroutine(
        description="The food arrived cold.",
        order_reference="ORD-123",
        acknowledgement_message="I've passed this to the restaurant team.",
        state={"rest_ref": "sfcs", "wa_name": "Lohith"},
        tool_call_id="tool-3",
        runtime=_runtime(events=events, contact_phone="01722 000000"),
    )

    assert events[0] == (
        "message",
        {
            "to": "447000000001",
            "text": (
                "Sorry, I couldn't pass your feedback to the restaurant team right "
                "now. Please call us on 01722 000000."
            ),
        },
    )
    assert events[1][0] == "service_selection"
    assert all("I've passed this" not in event[1].get("text", "") for event in events)
    assert command.goto == END
