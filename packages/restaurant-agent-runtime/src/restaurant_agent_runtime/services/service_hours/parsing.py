"""
Parsing helpers that normalize flexible service-hour inputs into the module's internal types
    . to_minutes accepts "HH:MM" strings (incl. HH >= 24), datetime.time, or int minutes
    . parse_intervals_for_day handles list-of-pair (str or int) entries and Interval instances
    . parse_week converts a raw {weekday_key: list[pair]} dict into {Weekday: list[Interval]}
    . Validates intra-day overlap; cross-day overflow is intentionally not validated
  Functions/Classes:
    . to_minutes
    . parse_intervals_for_day
    . parse_week
"""

from datetime import time

from .types import Interval, MAX_CLOSE_MIN, Weekday

TimeInput = str | int | time
IntervalInput = Interval | tuple | list


def to_minutes(value: TimeInput) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid time-of-day value: {value!r}")
    if isinstance(value, int):
        if not (0 <= value <= MAX_CLOSE_MIN):
            raise ValueError(f"Minutes out of range [0, {MAX_CLOSE_MIN}]: {value}")
        return value
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, str):
        parts = value.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Expected 'HH:MM', got {value!r}")
        try:
            hh, mm = int(parts[0]), int(parts[1])
        except ValueError as e:
            raise ValueError(f"Non-numeric time component in {value!r}") from e
        if hh < 0 or mm < 0 or mm >= 60:
            raise ValueError(f"Invalid time {value!r}")
        total = hh * 60 + mm
        if total > MAX_CLOSE_MIN:
            raise ValueError(f"Time {value!r} exceeds max {MAX_CLOSE_MIN} minutes")
        return total
    raise TypeError(f"Unsupported time input type: {type(value).__name__}")


def _coerce_interval(item: IntervalInput) -> Interval:
    if isinstance(item, Interval):
        return item
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return Interval(to_minutes(item[0]), to_minutes(item[1]))
    raise ValueError(f"Cannot parse interval from {item!r}")


def parse_intervals_for_day(raw: list) -> list[Interval]:
    intervals = [_coerce_interval(item) for item in raw]
    intervals.sort(key=lambda i: i.open_min)
    for prev, curr in zip(intervals, intervals[1:]):
        if curr.open_min < prev.close_min:
            raise ValueError(
                f"Overlapping intervals on the same day: {prev} and {curr}"
            )
    return intervals


def parse_week(raw: dict) -> dict[Weekday, list[Interval]]:
    result: dict[Weekday, list[Interval]] = {wd: [] for wd in Weekday}
    for key, day_intervals in raw.items():
        weekday = Weekday.from_key(key)
        result[weekday] = parse_intervals_for_day(day_intervals or [])
    return result
