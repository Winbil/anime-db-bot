from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PartialDate:
    """Calendar date with explicit source precision.

    Anime databases sometimes expose only a year or a year/month. Keeping that
    precision avoids inventing a day merely to fit ``datetime.date``.
    """

    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= int(self.year) <= 9999:
            raise ValueError("year must be in 1..9999")
        if self.month is None:
            if self.day is not None:
                raise ValueError("day requires month")
            return
        if not 1 <= int(self.month) <= 12:
            raise ValueError("month must be in 1..12")
        if self.day is None:
            return
        # ``date`` validates leap years and month-specific day ranges.
        date(int(self.year), int(self.month), int(self.day))

    @property
    def precision(self) -> str:
        if self.day is not None:
            return "day"
        if self.month is not None:
            return "month"
        return "year"

    def isoformat(self) -> str:
        result = f"{self.year:04d}"
        if self.month is not None:
            result += f"-{self.month:02d}"
        if self.day is not None:
            result += f"-{self.day:02d}"
        return result

    def __str__(self) -> str:
        return self.isoformat()


def _optional_int(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(str(value).strip())


def parse_partial_date(value: object) -> PartialDate | None:
    """Parse a date-like value without inventing missing precision."""
    if value is None or value == "":
        return None
    if isinstance(value, PartialDate):
        return value
    if isinstance(value, datetime):
        return PartialDate(value.year, value.month, value.day)
    if isinstance(value, date):
        return PartialDate(value.year, value.month, value.day)
    if isinstance(value, Mapping):
        try:
            year = _optional_int(value.get("year"))
            if year is None:
                return None
            return PartialDate(
                year,
                _optional_int(value.get("month")),
                _optional_int(value.get("day")),
            )
        except (TypeError, ValueError):
            return None

    raw = str(value).strip()
    if not raw:
        return None
    # Datetime strings are accepted, but this domain value intentionally keeps
    # only the date because episode UI historically displayed ``[:10]``.
    date_part = raw[:10] if "T" in raw or " " in raw else raw
    parts = date_part.split("-")
    if len(parts) not in {1, 2, 3} or not all(part.isdigit() for part in parts):
        return None
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) >= 2 else None
        day = int(parts[2]) if len(parts) == 3 else None
        return PartialDate(year, month, day)
    except ValueError:
        return None


def parse_datetime(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp, preserving its timezone information."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
