"""
Core types for the service_hours module
    . Weekday enum aligned with datetime.weekday() (Mon=0..Sun=6)
    . Interval is a frozen value object holding open/close minutes-since-midnight
    . close_min may exceed 1440 to encode overnight spans (e.g., 25:00 = 1am next day)
  Functions/Classes:
    . Weekday
    . Interval
"""

from dataclasses import dataclass
from enum import IntEnum

MINUTES_PER_DAY = 24 * 60
MAX_CLOSE_MIN = 2 * MINUTES_PER_DAY  # support up to 48:00 for overnight spans


class Weekday(IntEnum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6

    @classmethod
    def from_key(cls, key: str) -> "Weekday":
        return _KEY_TO_WEEKDAY[key.lower()]

    @property
    def key(self) -> str:
        return _WEEKDAY_TO_KEY[self]


_KEY_TO_WEEKDAY: dict[str, Weekday] = {
    "mon": Weekday.MON,
    "tue": Weekday.TUE,
    "wed": Weekday.WED,
    "thu": Weekday.THU,
    "fri": Weekday.FRI,
    "sat": Weekday.SAT,
    "sun": Weekday.SUN,
}

_WEEKDAY_TO_KEY: dict[Weekday, str] = {v: k for k, v in _KEY_TO_WEEKDAY.items()}


@dataclass(frozen=True, slots=True)
class Interval:
    open_min: int
    close_min: int

    def __post_init__(self):
        if not (0 <= self.open_min < self.close_min <= MAX_CLOSE_MIN):
            raise ValueError(
                f"Invalid interval: open_min={self.open_min}, close_min={self.close_min}; "
                f"require 0 <= open_min < close_min <= {MAX_CLOSE_MIN}"
            )

    @property
    def crosses_midnight(self) -> bool:
        return self.close_min > MINUTES_PER_DAY

    @property
    def overflow_min(self) -> int:
        """Minutes of this interval that spill into the next day. 0 if it doesn't overflow."""
        return max(0, self.close_min - MINUTES_PER_DAY)
