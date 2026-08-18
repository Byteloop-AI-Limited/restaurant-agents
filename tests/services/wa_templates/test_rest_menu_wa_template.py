from unittest.mock import AsyncMock

import pytest

from restaurant_agent_runtime.services.wa_templates.rest_menu_query_params import (
    RestMenuQueryParams,
)
from restaurant_agent_runtime.services.wa_templates import rest_menu_wa_template


@pytest.mark.asyncio
async def test_send_restaurant_menu_uses_text_cta_when_logo_is_not_configured(
    monkeypatch,
):
    operational_lookups = type(
        "OperationalLookups",
        (),
        {"get_app_url": lambda self, app_ref: "https://restaurant.example"},
    )()
    wa_client = AsyncMock()
    menu = RestMenuQueryParams(
        rest_ref="BNAT",
        minimum_order=0,
        order_type="takeaway",
        thread_id="thread-123",
        recipient="447448440754",
    )

    await rest_menu_wa_template.send_restaurant_menu_non_carousel(
        recipient="447448440754",
        rest_menu=menu,
        wa_client=wa_client,
        logo_url=None,
        operational_lookups=operational_lookups,
        delivery_promo_caption="20% off delivery",
        takeaway_promo_caption="Get started with your collection order",
    )

    wa_client.send_image.assert_not_awaited()
    wa_client.send_message.assert_awaited_once()
    kwargs = wa_client.send_message.await_args.kwargs
    assert kwargs["text"] == "Get started with your collection order"
    assert kwargs["buttons"].title == "Order Collection"
    assert kwargs["buttons"].url.startswith(
        "https://restaurant.example/restaurant/bnat?"
    )
