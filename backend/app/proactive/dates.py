"""Finding a deadline mentioned in free text ("please send it by Friday").

Only dates today or later are returned: a deadline in the past is not something to
create a task for. Rule-based and deliberately conservative: when the text is
ambiguous it returns nothing rather than guessing.
"""

import re
from datetime import date, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
]
_MONTH_PATTERN = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_PATTERN}\b", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b{_MONTH_PATTERN}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(next\s+|this\s+|coming\s+)?(" + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)
_IN_DAYS = re.compile(r"\b(?:in|within)\s+(\d{1,3})\s+days?\b", re.IGNORECASE)
_TODAY = re.compile(r"\b(today|tonight|eod|end of (?:the )?day|cob|close of business)\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_END_OF_WEEK = re.compile(r"\b(?:end of (?:the )?week|eow)\b", re.IGNORECASE)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_number(name: str) -> int:
    return _MONTHS.index(name[:3].lower()) + 1


def find_deadline(text: str, today: date) -> date | None:
    """The earliest date (today or later) that the text names, or None."""
    found: list[date | None] = []

    for match in _ISO.finditer(text):
        found.append(_safe_date(*map(int, match.groups())))

    for match in _DAY_MONTH.finditer(text):
        day, month = int(match.group(1)), _month_number(match.group(2))
        found.append(_this_or_next_year(day, month, today))
    for match in _MONTH_DAY.finditer(text):
        month, day = _month_number(match.group(1)), int(match.group(2))
        found.append(_this_or_next_year(day, month, today))

    if _TODAY.search(text):
        found.append(today)
    if _TOMORROW.search(text):
        found.append(today + timedelta(days=1))
    for match in _IN_DAYS.finditer(text):
        found.append(today + timedelta(days=int(match.group(1))))
    if _END_OF_WEEK.search(text):
        found.append(today + timedelta(days=(4 - today.weekday()) % 7))  # this Friday
    for match in _WEEKDAY.finditer(text):
        qualifier = (match.group(1) or "").strip().lower()
        ahead = (_WEEKDAYS.index(match.group(2).lower()) - today.weekday()) % 7
        if qualifier == "next" and ahead == 0:
            ahead = 7  # "next Monday" said on a Monday means a week away
        found.append(today + timedelta(days=ahead))

    upcoming = [d for d in found if d is not None and d >= today]
    return min(upcoming) if upcoming else None


def _this_or_next_year(day: int, month: int, today: date) -> date | None:
    candidate = _safe_date(today.year, month, day)
    if candidate is None:
        return None
    # "by 5 March" written in December means next March; a date only a few days
    # past is more likely a stale mention than a deadline a year away
    if candidate < today - timedelta(days=30):
        return _safe_date(today.year + 1, month, day)
    return candidate
