"""
Unit tests for restaurant_agent_runtime.rest_agent.agent_wa_senders.select_service_wa_send
    . Verifies the availability-filtered service menu: a recipient blocked by
      OperationalLookupCache.accepts_new_order sees only the enquiry button,
      while an Overwatch recipient (bypassed inside the cache) sees every
      button even when the venue is closed
    . Verifies operational_lookups is a required argument, so a forgotten
      argument raises immediately instead of silently rendering every button
  Functions/Classes:
    . FakeWaClient
    . FakeOperationalLookups
    . decode_button
    . test_select_service_wa_send_hides_closed_services_for_normal_recipient
    . test_select_service_wa_send_shows_all_buttons_for_overwatch_recipient_when_closed
    . test_select_service_wa_send_uses_app_owned_enquiry_button_label
    . test_select_service_wa_send_shows_all_buttons_when_open
    . test_select_service_wa_send_shows_only_the_open_service
    . test_select_service_wa_send_requires_operational_lookups
"""

import json

import pytest

from restaurant_agent_runtime.rest_agent.agent_wa_senders import select_service_wa_send


class FakeWaClient:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


class FakeOperationalLookups:
    """Minimal double for the one method the sender depends on."""

    def __init__(self, *, delivery_open=True, takeaway_open=True, overwatch_recipients=()):
        self.delivery_open = delivery_open
        self.takeaway_open = takeaway_open
        self.overwatch_recipients = set(overwatch_recipients)
        self.calls = []

    def accepts_new_order(self, order_type, recipient):
        self.calls.append((order_type, recipient))
        if recipient in self.overwatch_recipients:
            return True
        return self.delivery_open if order_type == "delivery" else self.takeaway_open


def decode_button(button):
    return json.loads(button.callback_data)


async def test_select_service_wa_send_hides_closed_services_for_normal_recipient():
    wa = FakeWaClient()
    ops = FakeOperationalLookups(delivery_open=False, takeaway_open=False)

    await select_service_wa_send(
        "447000000001", wa, "bnat", operational_lookups=ops
    )

    message = wa.sent_messages[0]
    assert message["text"] == "How can I help you today?"
    assert [button.title for button in message["buttons"]] == ["More options"]
    assert ops.calls == [("delivery", "447000000001"), ("takeaway", "447000000001")]


async def test_select_service_wa_send_shows_all_buttons_for_overwatch_recipient_when_closed():
    wa = FakeWaClient()
    ops = FakeOperationalLookups(
        delivery_open=False,
        takeaway_open=False,
        overwatch_recipients={"447000000001"},
    )

    await select_service_wa_send(
        "447000000001",
        wa,
        "bnat",
        operational_lookups=ops,
        delivery_button_label="Delivery (15% off)",
        takeaway_button_label="Takeaway (10% off)",
    )

    message = wa.sent_messages[0]
    assert [button.title for button in message["buttons"]] == [
        "Delivery (15% off)",
        "Takeaway (10% off)",
        "More options",
    ]
    payloads = [decode_button(button) for button in message["buttons"]]
    assert [payload["active_agent"] for payload in payloads] == [
        "delivery_agent",
        "takeaway_agent",
        "triage_agent",
    ]


async def test_select_service_wa_send_uses_app_owned_enquiry_button_label():
    wa = FakeWaClient()
    ops = FakeOperationalLookups(delivery_open=True, takeaway_open=True)

    await select_service_wa_send(
        "447000000001",
        wa,
        "bnat",
        operational_lookups=ops,
        enquiry_button_label="Something Else",
    )

    message = wa.sent_messages[0]
    assert [button.title for button in message["buttons"]] == [
        "Delivery",
        "Takeaway",
        "Something Else",
    ]


async def test_select_service_wa_send_shows_all_buttons_when_open():
    wa = FakeWaClient()
    ops = FakeOperationalLookups(delivery_open=True, takeaway_open=True)

    await select_service_wa_send(
        "447000000002", wa, "bnat", operational_lookups=ops
    )

    message = wa.sent_messages[0]
    assert [button.title for button in message["buttons"]] == [
        "Delivery",
        "Takeaway",
        "More options",
    ]


async def test_select_service_wa_send_shows_only_the_open_service():
    wa = FakeWaClient()
    ops = FakeOperationalLookups(delivery_open=True, takeaway_open=False)

    await select_service_wa_send(
        "447000000003", wa, "bnat", operational_lookups=ops
    )

    message = wa.sent_messages[0]
    assert [button.title for button in message["buttons"]] == ["Delivery", "More options"]


def test_select_service_wa_send_requires_operational_lookups():
    wa = FakeWaClient()

    with pytest.raises(TypeError):
        select_service_wa_send("447000000001", wa, "bnat")
