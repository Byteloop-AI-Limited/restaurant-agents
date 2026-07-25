"""
Unit tests for WhatsApp agent sender helpers
    . Loads agent_wa_senders with stubbed config and menu-template modules
    . Captures WhatsApp send_message calls without network access
    . Verifies button callback payloads, address/update flows, reservation links, and menu errors
  Functions/Classes:
    . FakeWaClient
    . sender_module
    . decode_button
    . test_callback_button_data_allows_extra_and_is_frozen
    . test_send_welcome_msg_wa_sends_personalized_text
    . test_select_service_wa_send_builds_three_callbacks
    . test_select_rest_ref_wa_send_builds_restaurant_callbacks
    . test_select_marketing_consent_wa_send_builds_yes_no_callbacks
    . test_send_something_else_options_for_chks_only_sends_contact
    . test_confirm_delivery_address_wa_uses_global_client_and_address_buttons
    . test_send_postcode_search_flow_builds_flow_button
    . test_send_update_address_wa_uses_rest_ref_in_url
    . test_reservation_link_wa_send_builds_url_button
    . test_send_restaurant_menu_returns_none_or_value_error
"""

import json
from types import ModuleType, SimpleNamespace

import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeWaClient:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


@pytest.fixture
def sender_module(monkeypatch):
    config_stub = build_config_stub()
    sent_menus = []

    template_module = ModuleType("restaurant_agent_core.services.wa_templates.rest_menu_wa_template")

    async def send_restaurant_menu_non_carousel(recipient, rest_menu, wa_client):
        sent_menus.append((recipient, rest_menu, wa_client))

    template_module.send_restaurant_menu_non_carousel = send_restaurant_menu_non_carousel

    params_module = load_module(
        "test_sender_rest_menu_query_params_module",
        "restaurant_agent_core.services/wa_templates/rest_menu_query_params.py",
        monkeypatch,
        {"config": config_stub},
    )

    module = load_module(
        "test_agent_wa_senders_module",
        "sfcs_agent.rest_agent/agent_wa_senders.py",
        monkeypatch,
        {
            "config": config_stub,
            "restaurant_agent_core.services.wa_templates.rest_menu_wa_template": template_module,
            "restaurant_agent_core.services.wa_templates.rest_menu_query_params": params_module,
        },
    )
    module.FlowButton = lambda **kwargs: SimpleNamespace(**kwargs)
    module._config_stub = config_stub
    module._sent_menus = sent_menus
    return module


def decode_button(button):
    return json.loads(button.callback_data)


def test_callback_button_data_allows_extra_and_is_frozen(sender_module):
    callback = sender_module.CallbackButtonData(action="/A", rest_ref="elas")

    assert callback.rest_ref == "elas"
    with pytest.raises(Exception):
        callback.action = "/B"


@pytest.mark.asyncio
async def test_send_welcome_msg_wa_sends_personalized_text(sender_module):
    wa = FakeWaClient()

    await sender_module.send_welcome_msg_wa("447000000001", "Bas", wa)

    assert len(wa.sent_messages) == 1
    text = wa.sent_messages[0]["text"]
    assert wa.sent_messages[0]["to"] == "447000000001"
    assert "Hi Bas" in text
    assert "AI Assistant" in text


@pytest.mark.asyncio
async def test_select_service_wa_send_builds_three_callbacks(sender_module):
    wa = FakeWaClient()

    await sender_module.select_service_wa_send("447000000001", wa, "elas")

    message = wa.sent_messages[0]
    assert message["text"] == "How can I help you today?"
    assert [button.title for button in message["buttons"]] == [
        "Delivery (20% off)",
        "Collection (15% off)",
        "Inquiry",
    ]
    payloads = [decode_button(button) for button in message["buttons"]]
    assert [payload["active_agent"] for payload in payloads] == [
        "delivery_agent",
        "takeaway_agent",
        "triage_agent",
    ]
    assert {payload["rest_ref"] for payload in payloads} == {"elas"}


@pytest.mark.skip(reason="SFCS is single-restaurant; select_rest_ref_wa_send does not exist")
@pytest.mark.asyncio
async def test_select_rest_ref_wa_send_builds_restaurant_callbacks(sender_module):
    wa = FakeWaClient()

    await sender_module.select_rest_ref_wa_send("447000000001", wa)

    buttons = wa.sent_messages[0]["buttons"]
    assert [button.title for button in buttons] == ["Elai", "Wings and Things"]
    assert [decode_button(button)["rest_ref"] for button in buttons] == ["elas", "chks"]


@pytest.mark.asyncio
async def test_select_marketing_consent_wa_send_builds_yes_no_callbacks(sender_module):
    wa = FakeWaClient()

    await sender_module.select_marketing_consent_wa_send("447000000001", wa, "elas")

    buttons = wa.sent_messages[0]["buttons"]
    assert [button.title for button in buttons] == ["Yes", "No"]
    assert [decode_button(button)["response"] for button in buttons] == ["yes", "no"]


@pytest.mark.skip(reason="SFCS does not have send_something_else_options_wa (elai multi-restaurant helper)")
@pytest.mark.asyncio
async def test_send_something_else_options_for_chks_only_sends_contact(sender_module):
    wa = FakeWaClient()

    await sender_module.send_something_else_options_wa("447000000001", wa, "chks")

    buttons = wa.sent_messages[0]["buttons"]
    assert [button.title for button in buttons] == ["Contact"]
    assert decode_button(buttons[0])["rest_ref"] == "chks"


@pytest.mark.asyncio
async def test_confirm_delivery_address_wa_uses_global_client_and_address_buttons(sender_module):
    await sender_module.confirm_delivery_address_wa(
        "447000000001",
        {
            "house_number": "10",
            "building": "Apt 2",
            "street_name": "High Street",
            "city": "London",
            "postcode": "BR6 6DN",
        },
    )

    message = sender_module._async_wa_client.sent_messages[0]
    assert message["header"] == "Confirm or Update Delivery Address"
    assert "10 Apt 2" in message["text"]
    assert [button.title for button in message["buttons"]] == ["Yes", "Update"]
    assert [decode_button(button)["response"] for button in message["buttons"]] == ["Yes", "No"]


@pytest.mark.asyncio
async def test_send_postcode_search_flow_builds_flow_button(sender_module):
    await sender_module.send_postcode_search_flow("447000000001", postcode_init="BR6 6DN")

    message = sender_module._async_wa_client.sent_messages[0]
    button = message["buttons"]
    assert button.title == "Update Address"
    assert button.flow_name == "PostcodeSearch"
    assert button.flow_action_payload["customer_id"] == "447000000001"
    assert button.flow_action_payload["postcode_init"] == "BR6 6DN"


@pytest.mark.asyncio
async def test_send_update_address_wa_uses_rest_ref_in_url(sender_module):
    wa = FakeWaClient()

    await sender_module.send_update_address_wa("447000000001", wa)

    button = wa.sent_messages[0]["buttons"]
    assert button.title == "Update Address"
    assert button.url == "https://restaurant.ordelo.app/address-update?recipient=447000000001&rest_ref=sfcs"


@pytest.mark.asyncio
async def test_reservation_link_wa_send_builds_url_button(sender_module):
    wa = FakeWaClient()

    await sender_module.reservation_link_wa_send(
        "447000000001", "https://book.test", wa=wa, wa_name="Bas"
    )

    message = wa.sent_messages[0]
    assert message["header"] == "Table Reservation"
    assert "Hi Bas!" in message["text"]
    assert message["buttons"].url == "https://book.test"


@pytest.mark.asyncio
async def test_send_restaurant_menu_returns_none_or_value_error(sender_module, monkeypatch):
    wa = FakeWaClient()

    result = await sender_module.send_restaurant_menu(
        recipient="447000000001",
        thread_id="thread-1",
        minimum_order=12,
        rest_ref="elas",
        _async_wa_client=wa,
    )

    assert result is None
    assert sender_module._sent_menus[0][0] == "447000000001"

    async def raise_value_error(*args, **kwargs):
        raise ValueError("bad menu")

    monkeypatch.setattr(sender_module, "send_restaurant_menu_non_carousel", raise_value_error)

    err = await sender_module.send_restaurant_menu(
        recipient="447000000001",
        thread_id="thread-1",
        minimum_order=12,
        rest_ref="elas",
        _async_wa_client=wa,
    )

    assert isinstance(err, ValueError)
    assert str(err) == "bad menu"
