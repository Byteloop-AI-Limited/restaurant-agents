"""
service_hours package - weekly service-hour schedule with overnight support
    . Exports WeeklySchedule, Interval, Weekday for module consumers
"""

from .schedule import WeeklySchedule
from .types import Interval, Weekday

__all__ = ["WeeklySchedule", "Interval", "Weekday"]
