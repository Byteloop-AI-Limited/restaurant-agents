"""
Weekly service-hours schedule
    . Models a 7-day recurring schedule with per-day intervals and overnight overflow
    . Bound to a ZoneInfo at construction; methods accept aware datetimes
    . Public API: is_open, next_open, current_interval, format_today
    . Storage shape (JSONB): {"mon": [["12:00", "21:30"]], "fri": [["16:00", "25:00"]], ...}
  Functions/Classes:
    . WeeklySchedule
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .formatting import format_minutes
from .parsing import parse_week
from .types import Interval, Weekday


NEW_ORDER_CUTOFF_MINUTES = 15


class WeeklySchedule:
    __slots__ = ("_intervals", "tz")

    def __init__(
        self, intervals_by_day: dict[Weekday, list[Interval]], tz: ZoneInfo
    ):
        self._intervals: dict[Weekday, list[Interval]] = {
            wd: sorted(intervals_by_day.get(wd, []), key=lambda i: i.open_min)
            for wd in Weekday
        }
        self.tz = tz

    @classmethod
    def from_dict(cls, raw: dict, tz: ZoneInfo) -> "WeeklySchedule":
        return cls(parse_week(raw), tz)

    def intervals_for(self, day: Weekday) -> list[Interval]:
        return list(self._intervals[day])

    def is_open(self, at: datetime) -> bool:
        return self.current_interval(at) is not None

    def current_interval(self, at: datetime) -> Interval | None:
        local = self._to_local(at)
        today = Weekday(local.weekday())
        now_min = local.hour * 60 + local.minute

        for interval in self._intervals[today]:
            if interval.open_min <= now_min < interval.close_min:
                return interval

        prev = Weekday((today - 1) % 7)
        for interval in self._intervals[prev]:
            if interval.crosses_midnight and now_min < interval.overflow_min:
                return interval

        return None

    def next_open(self, at: datetime) -> datetime | None:
        if self.is_open(at):
            return at

        local = self._to_local(at)
        today = Weekday(local.weekday())
        now_min = local.hour * 60 + local.minute
        local_date = local.date()

        for offset in range(8):
            day = Weekday((today + offset) % 7)
            candidates = self._intervals[day]
            if offset == 0:
                candidates = [i for i in candidates if i.open_min > now_min]
            if candidates:
                opening = candidates[0].open_min
                target_date = local_date + timedelta(days=offset)
                hh, mm = divmod(opening, 60)
                return datetime(
                    target_date.year,
                    target_date.month,
                    target_date.day,
                    hh,
                    mm,
                    tzinfo=self.tz,
                )

        return None

    def format_today(self, at: datetime) -> str:
        nxt = self.next_open(at)
        if nxt is None:
            return "We are currently unavailable. Please try again later."

        local_at = self._to_local(at)
        local_nxt = nxt.astimezone(self.tz)
        time_str = format_minutes(local_nxt.hour * 60 + local_nxt.minute)

        if local_nxt.date() == local_at.date():
            return f"We are currently closed. We open today at {time_str}."

        weekday_name = local_nxt.strftime("%A")
        return f"We are currently closed. We open {weekday_name} at {time_str}."

    def accepts_new_orders(self, at: datetime) -> bool:
        """Return whether the current service interval still accepts a new order.

        New delivery and takeaway orders close 15 minutes before the end of each
        active service interval. Venue opening remains independent from this
        new-order cut-off, including for intervals that continue past midnight.
        """
        interval = self.current_interval(at)
        if interval is None:
            return False

        local = self._to_local(at)
        now_min = local.hour * 60 + local.minute
        today = Weekday(local.weekday())
        if interval not in self._intervals[today] and interval.crosses_midnight:
            now_min += 24 * 60
        return now_min < interval.close_min - NEW_ORDER_CUTOFF_MINUTES

    def format_week(self) -> str:
        """Return a compact, customer-readable weekly venue schedule."""
        return self._format_week(cutoff_minutes=0)

    def format_new_order_week(self) -> str:
        """Return new-order hours derived from the venue schedule.

        Each service interval ends 15 minutes before the venue closes. This is
        intentionally derived from ``service_hours_json`` rather than stored as
        a separate RestaurantMaster setting.
        """
        return self._format_week(cutoff_minutes=NEW_ORDER_CUTOFF_MINUTES)

    def _format_week(self, *, cutoff_minutes: int) -> str:
        rendered: list[str] = []
        for day in Weekday:
            intervals = self._intervals[day]
            if not intervals:
                value = "closed"
            else:
                value = ", ".join(
                    f"{format_minutes(iv.open_min)}–{format_minutes(iv.close_min - cutoff_minutes)}"
                    for iv in intervals
                    if iv.close_min - cutoff_minutes > iv.open_min
                ) or "closed"
            rendered.append(f"{day.key.title()}: {value}")
        return "; ".join(rendered)

    def _to_local(self, at: datetime) -> datetime:
        if at.tzinfo is None:
            raise ValueError("WeeklySchedule requires an aware datetime")
        return at.astimezone(self.tz)

    def __repr__(self) -> str:
        days = {
            wd.key: [(iv.open_min, iv.close_min) for iv in ivs]
            for wd, ivs in self._intervals.items()
        }
        return f"WeeklySchedule(tz={self.tz}, intervals={days})"

    @property
    def is_permanently_closed(self) -> bool:
        return all(not ivs for ivs in self._intervals.values())

    def to_dict_minutes(self) -> dict[str, list[list[int]]]:
        """Serialize to {weekday_key: [[open_min, close_min], ...]} for diagnostics."""
        return {
            wd.key: [[iv.open_min, iv.close_min] for iv in ivs]
            for wd, ivs in self._intervals.items()
        }
