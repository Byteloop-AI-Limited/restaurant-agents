"""
Unit tests for restaurant menu query parameter model
    . Covers URL query serialization and excluded restaurant reference
    . Verifies recipient pattern, order type, and numeric validation
  Functions/Classes:
    . test_to_query_params_excludes_rest_ref_and_none_distance
    . test_to_query_params_includes_distance_when_present
    . test_validation_rejects_invalid_recipient_order_type_and_negative_values
"""

import pytest
from pydantic import ValidationError

from restaurant_agent_runtime.services.wa_templates.rest_menu_query_params import RestMenuQueryParams


def test_to_query_params_excludes_rest_ref_and_none_distance():
    params = RestMenuQueryParams(
        rest_ref="elas",
        minimum_order=12,
        order_type="delivery",
        thread_id="thread-1",
        recipient="447000000001",
    )

    assert params.to_query_params() == (
        "minimum_order=12.0&order_type=delivery&thread_id=thread-1&recipient=447000000001"
    )


def test_to_query_params_includes_distance_when_present():
    params = RestMenuQueryParams(
        distance=1.5,
        minimum_order=0,
        order_type="takeaway",
        thread_id="thread-1",
        recipient="447000000001",
    )

    assert params.to_query_params() == (
        "distance=1.5&minimum_order=0.0&order_type=takeaway&thread_id=thread-1&recipient=447000000001"
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"recipient": "447"},
        {"order_type": "dinein"},
        {"minimum_order": -1},
        {"distance": -0.1},
    ],
)
def test_validation_rejects_invalid_recipient_order_type_and_negative_values(kwargs):
    data = {
        "minimum_order": 12,
        "order_type": "delivery",
        "thread_id": "thread-1",
        "recipient": "447000000001",
    }
    data.update(kwargs)

    with pytest.raises(ValidationError):
        RestMenuQueryParams(**data)
