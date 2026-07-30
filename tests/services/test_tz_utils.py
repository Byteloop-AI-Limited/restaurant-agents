"""
Unit tests for UK timezone utility helpers
    . Covers ISO parsing with trailing Z timestamps
    . Covers UK display formatting from strings and datetimes
    . Covers epoch conversion through UK timezone coercion
  Functions/Classes:
    . test_parse_db_iso_handles_z_suffix
    . test_fmt_uk_time_from_string_and_datetime
    . test_to_uk_epoch_returns_int
"""

from datetime import datetime, timezone

from restaurant_agent_runtime.services import tz_utils


def test_parse_db_iso_handles_z_suffix():
    parsed = tz_utils.parse_db_iso("2026-05-09T10:30:00Z")

    assert parsed == datetime(2026, 5, 9, 10, 30, tzinfo=timezone.utc)


def test_fmt_uk_time_from_string_and_datetime():
    assert tz_utils.fmt_uk_time("2026-05-09T10:30:00Z") == "11:30 AM"
    assert tz_utils.fmt_uk_time(datetime(2026, 1, 9, 10, 30, tzinfo=timezone.utc)) == "10:30 AM"


def test_to_uk_epoch_returns_int():
    assert isinstance(tz_utils.to_uk_epoch("2026-05-09T10:30:00Z"), int)
