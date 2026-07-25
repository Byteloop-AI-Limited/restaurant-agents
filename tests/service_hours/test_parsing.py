from datetime import time

import pytest

from restaurant_agent_core.services.service_hours.parsing import (
    parse_intervals_for_day,
    parse_week,
    to_minutes,
)
from restaurant_agent_core.services.service_hours.types import Interval, Weekday


def test_to_minutes_string():
    assert to_minutes("00:00") == 0
    assert to_minutes("12:00") == 720
    assert to_minutes("16:30") == 990
    assert to_minutes("21:30") == 1290


def test_to_minutes_overnight_string():
    assert to_minutes("24:00") == 1440
    assert to_minutes("25:00") == 1500
    assert to_minutes("28:30") == 1710


def test_to_minutes_time_object():
    assert to_minutes(time(16, 0)) == 960
    assert to_minutes(time(0, 0)) == 0


def test_to_minutes_int_passthrough():
    assert to_minutes(960) == 960
    assert to_minutes(0) == 0
    assert to_minutes(1500) == 1500


def test_to_minutes_invalid():
    with pytest.raises(ValueError):
        to_minutes("not-a-time")
    with pytest.raises(ValueError):
        to_minutes("12:99")
    with pytest.raises(ValueError):
        to_minutes("12")
    with pytest.raises(ValueError):
        to_minutes(-1)
    with pytest.raises(ValueError):
        to_minutes(99999)
    with pytest.raises(TypeError):
        to_minutes(object())


def test_to_minutes_rejects_bool():
    with pytest.raises(ValueError):
        to_minutes(True)


def test_parse_intervals_for_day_pairs():
    result = parse_intervals_for_day([["12:00", "21:30"]])
    assert result == [Interval(720, 1290)]


def test_parse_intervals_for_day_split_shift_sorted():
    result = parse_intervals_for_day([["18:00", "22:00"], ["12:00", "15:00"]])
    assert result == [Interval(720, 900), Interval(1080, 1320)]


def test_parse_intervals_for_day_overnight():
    result = parse_intervals_for_day([["16:00", "25:00"]])
    assert result == [Interval(960, 1500)]


def test_parse_intervals_for_day_overlap_raises():
    with pytest.raises(ValueError, match="Overlapping"):
        parse_intervals_for_day([["12:00", "16:00"], ["15:00", "20:00"]])


def test_parse_intervals_accepts_int_pairs():
    assert parse_intervals_for_day([[720, 1290]]) == [Interval(720, 1290)]


def test_parse_week_full():
    raw = {
        "mon": [["12:00", "21:30"]],
        "fri": [["16:00", "25:00"]],
        "sat": [],
    }
    result = parse_week(raw)
    assert result[Weekday.MON] == [Interval(720, 1290)]
    assert result[Weekday.FRI] == [Interval(960, 1500)]
    assert result[Weekday.SAT] == []
    assert result[Weekday.TUE] == []
    assert result[Weekday.SUN] == []


def test_parse_week_unknown_key_raises():
    with pytest.raises(KeyError):
        parse_week({"funday": [["12:00", "13:00"]]})
