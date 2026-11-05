"""Business-day helpers. The simulated plant works Monday to Friday."""

from collections.abc import Iterator
from datetime import date, timedelta


def is_business_day(day: date) -> bool:
    return day.weekday() < 5


def roll_forward(day: date) -> date:
    """Move a date to the next business day if it falls on a weekend."""
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def add_business_days(day: date, n: int) -> date:
    """Add (or subtract, if n < 0) n business days."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        day += timedelta(days=step)
        if is_business_day(day):
            remaining -= 1
    return day


def business_days(start: date, calendar_days: int) -> Iterator[date]:
    """Business days inside [start, start + calendar_days)."""
    for offset in range(calendar_days):
        day = start + timedelta(days=offset)
        if is_business_day(day):
            yield day


def erp_date(day: date) -> str:
    """ERP extracts store dates as YYYYMMDD text."""
    return day.strftime("%Y%m%d")
