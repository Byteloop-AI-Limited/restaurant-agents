"""
Unit tests for pricing microservice client logic
    . Loads pricing logic with stubbed config to avoid real settings imports
    . Mocks requests.post to avoid network calls
    . Covers request payload construction, car-option selection, and error passthrough
  Functions/Classes:
    . pricing_module
    . FakeResponse
    . test_get_final_order_value_posts_payload_and_returns_car_option
    . test_get_final_order_value_returns_status_and_text_on_error
    . test_get_final_order_value_returns_last_option_when_no_car_option
"""

import pytest

from tests._stubs.config_stub import build_config_stub
from tests._stubs.loader import load_module


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


@pytest.fixture
def pricing_module(monkeypatch):
    config_stub = build_config_stub()
    return load_module(
        "test_pricing_logic_module",
        "restaurant_agent_runtime.services/pricing_ms/pricing_logic.py",
        monkeypatch,
        {"config": config_stub},
    )


def test_get_final_order_value_posts_payload_and_returns_car_option(monkeypatch, pricing_module):
    calls = []

    def fake_post(url, json, headers):
        calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(
            json_data={
                "delivery_options": [
                    {"vehicle_type": "bike", "final_order_value": 18},
                    {"vehicle_type": "car", "final_order_value": 20},
                ]
            }
        )

    monkeypatch.setattr(pricing_module.requests, "post", fake_post)

    result = pricing_module.get_final_order_value(
        order_number="ORD-1",
        cust_lat=51.1,
        cust_lon=0.1,
        total_food_value=15.0,
        rest_lat=51.2,
        rest_lon=0.2,
    )

    assert result == {"vehicle_type": "car", "final_order_value": 20}
    assert calls == [
        {
            "url": "https://pricing.test/calculate",
            "json": {
                "order_number": "ORD-1",
                "total_food_value": 15.0,
                "restaurant_latitude": 51.2,
                "restaurant_longitude": 0.2,
                "customer_latitude": 51.1,
                "customer_longitude": 0.1,
            },
            "headers": {"Content-Type": "application/json"},
        }
    ]


def test_get_final_order_value_returns_status_and_text_on_error(monkeypatch, pricing_module):
    monkeypatch.setattr(
        pricing_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(status_code=503, text="unavailable"),
    )

    assert pricing_module.get_final_order_value("ORD-1", 1, 2, 3, 4, 5) == (
        503,
        "unavailable",
    )


def test_get_final_order_value_returns_last_option_when_no_car_option(monkeypatch, pricing_module):
    monkeypatch.setattr(
        pricing_module.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            json_data={"delivery_options": [{"vehicle_type": "bike"}]}
        ),
    )

    assert pricing_module.get_final_order_value("ORD-1", 1, 2, 3, 4, 5) == {
        "vehicle_type": "bike"
    }
