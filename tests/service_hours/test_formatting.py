import pytest

from restaurant_agent_core.services.service_hours.formatting import format_minutes


def test_midnight():
    assert format_minutes(0) == "12 am"


def test_noon():
    assert format_minutes(720) == "12 pm"


def test_morning():
    assert format_minutes(540) == "9 am"
    assert format_minutes(570) == "9:30 am"


def test_evening():
    assert format_minutes(1290) == "9:30 pm"
    assert format_minutes(1380) == "11 pm"


def test_overnight_wraps_to_next_day_clock():
    assert format_minutes(1500) == "1 am"  # 25:00
    assert format_minutes(1530) == "1:30 am"  # 25:30


def test_negative_raises():
    with pytest.raises(ValueError):
        format_minutes(-1)
