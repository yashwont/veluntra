from collections.abc import Sequence

from app.integrations.google.types import CalendarEvent


def find_conflicts(events: Sequence[CalendarEvent]) -> list[tuple[CalendarEvent, CalendarEvent]]:
    """Pairs of events that overlap in time.

    All-day events (birthdays, "out of office" banners) and events the user has
    declined don't occupy their time, so they never conflict. Events that merely
    touch (one ends exactly when the next starts) are not a conflict.
    """
    timed = sorted(
        (e for e in events if not e.all_day and not e.declined), key=lambda e: (e.start, e.end)
    )
    conflicts: list[tuple[CalendarEvent, CalendarEvent]] = []
    for i, first in enumerate(timed):
        for second in timed[i + 1 :]:
            if second.start >= first.end:
                break  # sorted by start: nothing later can overlap `first`
            conflicts.append((first, second))
    return conflicts
