from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from restaurant_agent_runtime.services.service_hours import WeeklySchedule
from restaurant_agent_runtime.services.service_hours.types import Interval

UK = ZoneInfo("Europe/London")


def _ws(raw: dict) -> WeeklySchedule:
    return WeeklySchedule.from_dict(raw, tz=UK)


# 2025-12-01 = Monday in UK (a stable historical date).
# 2025-12-05 = Friday, 2025-12-06 = Saturday, 2025-12-07 = Sunday.
def _at(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UK)


def test_permanently_closed():
    ws = _ws({})
    assert ws.is_open(_at(2025, 12, 1, 12)) is False
    assert ws.next_open(_at(2025, 12, 1, 12)) is None
    assert ws.is_permanently_closed is True


def test_uniform_week_mimics_legacy():
    raw = {d: [["12:00", "21:30"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    ws = _ws(raw)
    assert ws.is_open(_at(2025, 12, 1, 12)) is True
    assert ws.is_open(_at(2025, 12, 1, 11, 59)) is False
    assert ws.is_open(_at(2025, 12, 1, 21, 29)) is True
    assert ws.is_open(_at(2025, 12, 1, 21, 30)) is False  # exclusive close


def test_split_shift_lunch_and_dinner():
    ws = _ws({"mon": [["12:00", "15:00"], ["18:00", "22:00"]]})
    assert ws.is_open(_at(2025, 12, 1, 13)) is True
    assert ws.is_open(_at(2025, 12, 1, 16)) is False  # gap
    assert ws.is_open(_at(2025, 12, 1, 19)) is True
    assert ws.is_open(_at(2025, 12, 1, 23)) is False


def test_overnight_friday_to_saturday():
    ws = _ws({"fri": [["16:00", "25:00"]]})
    assert ws.is_open(_at(2025, 12, 5, 16)) is True  # Fri 4pm
    assert ws.is_open(_at(2025, 12, 5, 23, 59)) is True  # Fri just before midnight
    assert ws.is_open(_at(2025, 12, 6, 0, 30)) is True  # Sat 12:30am — Friday's overflow
    assert ws.is_open(_at(2025, 12, 6, 0, 59)) is True  # Sat 12:59am
    assert ws.is_open(_at(2025, 12, 6, 1, 0)) is False  # Sat 1am — closed (exclusive)
    assert ws.is_open(_at(2025, 12, 5, 15, 59)) is False  # Fri 3:59pm — before opening


def test_current_interval_returns_active():
    ws = _ws({"mon": [["12:00", "15:00"], ["18:00", "22:00"]]})
    assert ws.current_interval(_at(2025, 12, 1, 13)) == Interval(720, 900)
    assert ws.current_interval(_at(2025, 12, 1, 19)) == Interval(1080, 1320)
    assert ws.current_interval(_at(2025, 12, 1, 16)) is None


def test_next_open_when_open_returns_at():
    ws = _ws({"mon": [["12:00", "21:30"]]})
    at = _at(2025, 12, 1, 13)
    assert ws.next_open(at) == at


def test_next_open_later_today():
    ws = _ws({"mon": [["12:00", "15:00"], ["18:00", "22:00"]]})
    at = _at(2025, 12, 1, 16)
    assert ws.next_open(at) == _at(2025, 12, 1, 18)


def test_next_open_rolls_to_next_day():
    ws = _ws({"mon": [["12:00", "21:30"]], "tue": [["12:00", "21:30"]]})
    at = _at(2025, 12, 1, 23)  # Mon 11pm, after close
    assert ws.next_open(at) == _at(2025, 12, 2, 12)


def test_next_open_skips_closed_days():
    # Sun closed, Mon open
    ws = _ws({"sat": [["12:00", "22:00"]], "mon": [["12:00", "21:30"]]})
    at = _at(2025, 12, 6, 23)  # Sat 11pm
    assert ws.next_open(at) == _at(2025, 12, 8, 12)  # next Monday


def test_format_today_open_today_later():
    ws = _ws({"mon": [["12:00", "15:00"], ["18:00", "22:00"]]})
    at = _at(2025, 12, 1, 16)
    assert ws.format_today(at) == "We are currently closed. We open today at 6 pm."


def test_format_today_open_another_day():
    ws = _ws({"sat": [["12:00", "22:00"]], "mon": [["12:00", "21:30"]]})
    at = _at(2025, 12, 6, 23)  # Sat 11pm — next is Mon
    assert ws.format_today(at) == "We are currently closed. We open Monday at 12 pm."


def test_format_today_permanently_closed():
    ws = _ws({})
    at = _at(2025, 12, 1, 12)
    assert ws.format_today(at) == "We are currently unavailable. Please try again later."


def test_naive_datetime_rejected():
    ws = _ws({"mon": [["12:00", "21:30"]]})
    with pytest.raises(ValueError, match="aware"):
        ws.is_open(datetime(2025, 12, 1, 12))


def test_to_dict_minutes_roundtrip_shape():
    raw = {"mon": [["12:00", "21:30"]], "fri": [["16:00", "25:00"]]}
    ws = _ws(raw)
    out = ws.to_dict_minutes()
    assert out["mon"] == [[720, 1290]]
    assert out["fri"] == [[960, 1500]]
    assert out["sat"] == []
