"""Chilean business-calendar operations used by all calculations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta


def _easter_sunday(year: int) -> date:
    """Return Gregorian Easter using the Meeus/Jones/Butcher algorithm."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    easter_weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * easter_weekday_offset) // 451
    month = (h + easter_weekday_offset - 7 * m + 114) // 31
    day = (h + easter_weekday_offset - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def chilean_holidays(year: int) -> frozenset[date]:
    """Return the nationally observed Chilean holidays for ``year``.

    Variable holidays are included explicitly (Good Friday, Holy Saturday
    and the Indigenous Peoples' Day).  The caller can add regional or
    one-off holidays through ``BusinessCalendar``.
    """

    fixed = {
        date(year, 1, 1),
        date(year, 5, 1),
        date(year, 5, 21),
        date(year, 6, 29),
        date(year, 7, 16),
        date(year, 8, 15),
        date(year, 9, 18),
        date(year, 9, 19),
        date(year, 10, 12),
        date(year, 10, 31),
        date(year, 11, 1),
        date(year, 12, 8),
        date(year, 12, 25),
    }
    easter = _easter_sunday(year)
    # Chile observes this holiday on the southern-winter solstice.  For the
    # Gregorian years used by the project data, the civil date is June 21.
    indigenous_day = date(year, 6, 21)
    movable = {
        easter - timedelta(days=2),
        easter - timedelta(days=1),
        indigenous_day,
    }
    return frozenset(fixed | movable)


class BusinessCalendar:
    """Weekday/holiday calendar with optional resource exceptions."""

    def __init__(
        self,
        holidays: Iterable[date] = (),
        non_working_weekdays: Iterable[int] = (5, 6),
        resource_exceptions: Mapping[str, Iterable[date]] | None = None,
    ) -> None:
        self.holidays = frozenset(holidays)
        self.non_working_weekdays = frozenset(non_working_weekdays)
        self.resource_exceptions = {
            resource_id: frozenset(days)
            for resource_id, days in (resource_exceptions or {}).items()
        }

    @classmethod
    def chile(cls, years: Iterable[int]) -> BusinessCalendar:
        """Build a Monday-Friday Chilean calendar for the supplied years."""

        holidays = {holiday for year in years for holiday in chilean_holidays(year)}
        return cls(holidays=holidays)

    def is_working_day(self, day: date, resource_id: str | None = None) -> bool:
        """Whether ``day`` is available for the project/resource."""

        if day.weekday() in self.non_working_weekdays or day in self.holidays:
            return False
        if resource_id is not None and day in self.resource_exceptions.get(resource_id, ()):
            return False
        return True

    def next_working_day(self, day: date, resource_id: str | None = None) -> date:
        """Return ``day`` or the next available day."""

        current = day
        while not self.is_working_day(current, resource_id):
            current += timedelta(days=1)
        return current

    def previous_working_day(self, day: date, resource_id: str | None = None) -> date:
        """Return ``day`` or the previous available day."""

        current = day
        while not self.is_working_day(current, resource_id):
            current -= timedelta(days=1)
        return current

    def add_working_days(
        self, start: date, offset: int, resource_id: str | None = None
    ) -> date:
        """Move by business-day positions, normalizing a non-working anchor."""

        current = (
            self.next_working_day(start, resource_id)
            if offset >= 0
            else self.previous_working_day(start, resource_id)
        )
        step = 1 if offset >= 0 else -1
        remaining = abs(offset)
        while remaining:
            current += timedelta(days=step)
            if self.is_working_day(current, resource_id):
                remaining -= 1
        return current

    def duration_finish(
        self, start: date, duration_days: int, resource_id: str | None = None
    ) -> date:
        """Calculate inclusive finish for a duration in business days."""

        if duration_days < 0:
            raise ValueError("La duración no puede ser negativa")
        return self.add_working_days(start, max(duration_days - 1, 0), resource_id)

    def working_days_between(self, start: date, end: date) -> int:
        """Return signed business-day distance between two working dates."""

        if start == end:
            return 0
        if end > start:
            current, total = start, 0
            while current < end:
                if self.is_working_day(current):
                    total += 1
                current += timedelta(days=1)
            return total
        return -self.working_days_between(end, start)

    def working_days_inclusive(self, start: date, end: date) -> int:
        """Count working days in an inclusive interval."""

        if end < start:
            return 0
        return self.working_days_between(start, end) + int(self.is_working_day(end))
