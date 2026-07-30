"""
UK timezone utilities
    . Provides UK_TZ ZoneInfo and helpers for parsing and formatting timestamps
    . Used by service_hours module and webhook handlers for consistent UK-time handling
  Functions/Classes:
    . parse_db_iso - Parse Supabase ISO timestamp (handles trailing Z)
    . fmt_uk_time - Format an ISO string or datetime as UK 12-hour time
    . to_uk_epoch - Convert an ISO string or datetime to a UK-zoned epoch int
"""

from datetime import datetime
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")


def parse_db_iso(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _coerce(iso_or_dt: str | datetime) -> datetime:
    return parse_db_iso(iso_or_dt) if isinstance(iso_or_dt, str) else iso_or_dt


def fmt_uk_time(iso_or_dt: str | datetime) -> str:
    return _coerce(iso_or_dt).astimezone(UK_TZ).strftime("%I:%M %p").lstrip("0")


def to_uk_epoch(iso_or_dt: str | datetime) -> int:
    return int(_coerce(iso_or_dt).astimezone(UK_TZ).timestamp())
