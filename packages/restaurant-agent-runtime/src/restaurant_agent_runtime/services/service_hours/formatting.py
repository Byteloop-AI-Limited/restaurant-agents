"""
Human-readable formatters for service-hour values
    . format_minutes renders minutes-since-midnight to a 12-hour clock string
    . Wraps overflow minutes (>= 1440) into the next day's clock
  Functions/Classes:
    . format_minutes
"""

from .types import MINUTES_PER_DAY


def format_minutes(minutes: int) -> str:
    """1290 -> '9:30 pm', 1500 -> '1 am' (next-day wrap), 720 -> '12 pm'."""
    if minutes < 0:
        raise ValueError(f"Negative minutes: {minutes}")
    wrapped = minutes % MINUTES_PER_DAY
    hh = wrapped // 60
    mm = wrapped % 60
    suffix = "am" if hh < 12 else "pm"
    hh_12 = hh % 12 or 12
    if mm:
        return f"{hh_12}:{mm:02d} {suffix}"
    return f"{hh_12} {suffix}"
