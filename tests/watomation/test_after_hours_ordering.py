from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.watomation.on_message_graph_handler import (
    is_ordering_request,
    send_closed_message,
)


def test_is_ordering_request_recognizes_delivery_and_collection_intent():
    assert is_ordering_request(SimpleNamespace(text="I want delivery"))
    assert is_ordering_request(SimpleNamespace(text="Can I collect an order?"))
    assert is_ordering_request(SimpleNamespace(text="Please send the menu"))
    assert not is_ordering_request(SimpleNamespace(text="Do you have parking?"))


@pytest.mark.asyncio
async def test_after_hours_ordering_uses_exact_closed_message():
    wa = SimpleNamespace(send_message=AsyncMock())
    msg = SimpleNamespace(sender="447000000001", text="I want collection")
    runtime = SimpleNamespace(operational_lookups=SimpleNamespace())

    await send_closed_message(wa, msg, runtime=runtime)

    wa.send_message.assert_awaited_once_with(
        to="447000000001", text="Ordering is currently closed."
    )


@pytest.mark.asyncio
async def test_after_hours_non_order_keeps_general_closed_reply():
    wa = SimpleNamespace(send_message=AsyncMock())
    msg = SimpleNamespace(sender="447000000001", text="Do you have parking?")
    runtime = SimpleNamespace(
        operational_lookups=SimpleNamespace(
            get_restaurant_master=lambda: SimpleNamespace(
                service_hours=SimpleNamespace(
                    format_today=lambda _at: "We are currently closed."
                )
            )
        )
    )

    await send_closed_message(wa, msg, runtime=runtime)

    wa.send_message.assert_awaited_once_with(
        to="447000000001",
        text="Thank you for your message. We are currently closed.",
    )
