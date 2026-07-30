"""
Unit tests for service-hours parsing, formatting, intervals, and weekly schedules
    . Covers time coercion, interval validation, week parsing, and human formatting
    . Covers timezone-aware schedule queries including overnight spillover intervals
    . Verifies permanently closed schedules and serialization helpers
  Functions/Classes:
    . dt
    . test_to_minutes_accepts_supported_inputs
    . test_to_minutes_rejects_invalid_inputs
    . test_parse_intervals_sorts_and_rejects_overlap
    . test_parse_week_handles_missing_days
    . test_interval_properties_and_validation
    . test_format_minutes_wraps_and_formats
    . test_weekly_schedule_open_closed_and_overnight
    . test_weekly_schedule_next_open_and_format_today
    . test_weekly_schedule_requires_aware_datetime
    . test_weekly_schedule_closed_helpers
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from restaurant_agent_runtime.services.service_hours.formatting import format_minutes
from restaurant_agent_runtime.services.service_hours.parsing import parse_intervals_for_day, parse_week, to_minutes
from restaurant_agent_runtime.services.service_hours.schedule import WeeklySchedule
from restaurant_agent_runtime.services.service_hours.types import Interval, Weekday


TZ = ZoneInfo("Europe/London")


def dt(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def test_to_minutes_accepts_supported_inputs():
    assert to_minutes("00:00") == 0
    assert to_minutes("25:30") == 1530
    assert to_minutes(90) == 90
    assert to_minutes(time(9, 15)) == 555


@pytest.mark.parametrize("value", [True, -1, 2881, "bad", "10", "10:60", "-1:00", object()])
def test_to_minutes_rejects_invalid_inputs(value):
    with pytest.raises((TypeError, ValueError)):
        to_minutes(value)


def test_parse_intervals_sorts_and_rejects_overlap():
    intervals = parse_intervals_for_day([["16:00", "17:00"], ["12:00", "14:00"]])
    assert [(i.open_min, i.close_min) for i in intervals] == [(720, 840), (960, 1020)]

    with pytest.raises(ValueError, match="Overlapping intervals"):
        parse_intervals_for_day([["12:00", "14:00"], ["13:30", "15:00"]])


def test_parse_week_handles_missing_days():
    parsed = parse_week({"mon": [["12:00", "14:00"]], "fri": None})
    assert parsed[Weekday.MON] == [Interval(720, 840)]
    assert parsed[Weekday.TUE] == []
    assert parsed[Weekday.FRI] == []


def test_interval_properties_and_validation():
    overnight = Interval(960, 1500)
    assert overnight.crosses_midnight is True
    assert overnight.overflow_min == 60
    assert Interval(720, 840).crosses_midnight is False
    assert Interval(720, 840).overflow_min == 0

    with pytest.raises(ValueError):
        Interval(100, 100)
    with pytest.raises(ValueError):
        Interval(-1, 100)
    with pytest.raises(ValueError):
        Interval(0, 2881)


def test_format_minutes_wraps_and_formats():
    assert format_minutes(0) == "12 am"
    assert format_minutes(60) == "1 am"
    assert format_minutes(720) == "12 pm"
    assert format_minutes(1290) == "9:30 pm"
    assert format_minutes(1500) == "1 am"

    with pytest.raises(ValueError):
        format_minutes(-1)


def test_weekly_schedule_open_closed_and_overnight():
    schedule = WeeklySchedule.from_dict(
        {"mon": [["12:00", "14:00"]], "fri": [["16:00", "25:00"]]},
        TZ,
    )

    assert schedule.is_open(dt(2026, 5, 4, 12, 30)) is True
    assert schedule.current_interval(dt(2026, 5, 4, 12, 30)) == Interval(720, 840)
    assert schedule.is_open(dt(2026, 5, 4, 15, 0)) is False
    assert schedule.is_open(dt(2026, 5, 9, 0, 30)) is True


def test_weekly_schedule_next_open_and_format_today():
    schedule = WeeklySchedule.from_dict(
        {"mon": [["12:00", "14:00"]], "wed": [["09:30", "11:00"]]},
        TZ,
    )

    assert schedule.next_open(dt(2026, 5, 4, 10, 0)) == dt(2026, 5, 4, 12, 0)
    assert schedule.next_open(dt(2026, 5, 4, 12, 30)) == dt(2026, 5, 4, 12, 30)
    assert schedule.next_open(dt(2026, 5, 5, 18, 0)) == dt(2026, 5, 6, 9, 30)
    assert schedule.format_today(dt(2026, 5, 4, 10, 0)) == "We are currently closed. We open today at 12 pm."
    assert schedule.format_today(dt(2026, 5, 5, 18, 0)) == "We are currently closed. We open Wednesday at 9:30 am."


def test_weekly_schedule_requires_aware_datetime():
    schedule = WeeklySchedule.from_dict({"mon": [["12:00", "14:00"]]}, TZ)
    with pytest.raises(ValueError, match="aware datetime"):
        schedule.is_open(datetime(2026, 5, 4, 12, 30))


def test_weekly_schedule_closed_helpers():
    schedule = WeeklySchedule.from_dict({}, TZ)
    assert schedule.is_permanently_closed is True
    assert schedule.next_open(dt(2026, 5, 4, 10, 0)) is None
    assert schedule.format_today(dt(2026, 5, 4, 10, 0)) == "We are currently unavailable. Please try again later."
    assert schedule.to_dict_minutes() == {wd.key: [] for wd in Weekday}
