"""Deadline parsing, action detection and task ranking: pure logic, no database."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.integrations.google.types import EmailSummary
from app.models.task import Task, TaskPriority, TaskStatus
from app.proactive.dates import find_deadline
from app.proactive.detectors import RuleBasedDetector, clean_subject, sender_name
from app.proactive.priorities import rank_tasks

TODAY = date(2026, 10, 7)  # a Wednesday


def test_the_reference_day_is_a_wednesday() -> None:
    assert TODAY.weekday() == 2


# --- Deadlines -----------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("please send it by tomorrow", date(2026, 10, 8)),
    ("need this today", TODAY),
    ("by EOD", TODAY),
    ("by end of day", TODAY),
    ("by Friday", date(2026, 10, 9)),
    ("on Wednesday", TODAY),
    ("next Wednesday", date(2026, 10, 14)),
    ("next Friday", date(2026, 10, 9)),
    ("this Monday", date(2026, 10, 12)),
    ("in 3 days", date(2026, 10, 10)),
    ("within 10 days", date(2026, 10, 17)),
    ("due 2026-10-15", date(2026, 10, 15)),
    ("by 15 October", date(2026, 10, 15)),
    ("by the 15th of October", date(2026, 10, 15)),
    ("deadline: Oct 15th", date(2026, 10, 15)),
    ("by end of the week", date(2026, 10, 9)),
    ("5 March", date(2027, 3, 5)),  # long past this year: means next year
    ("Friday or tomorrow, whichever is first", date(2026, 10, 8)),  # the earliest one
])
def test_deadlines_are_found(text: str, expected: date) -> None:
    assert find_deadline(text, TODAY) == expected


@pytest.mark.parametrize("text", [
    "no date here at all",
    "",
    "1 October",  # a few days ago: stale, not a deadline
    "2026-10-01",
    "30 February",  # not a real date
    "the 2026-13-45 thing",
])
def test_no_deadline_when_none_is_named(text: str) -> None:
    assert find_deadline(text, TODAY) is None


def test_end_of_week_on_a_weekend_is_not_in_the_past() -> None:
    saturday = date(2026, 10, 10)

    assert find_deadline("by end of week", saturday) == date(2026, 10, 16)


# --- Spotting requests in email -------------------------------------------------------------


def mail(subject: str, snippet: str = "", sender: str = "Ram Sharma <ram@abc.test>") -> EmailSummary:
    return EmailSummary(id="m", thread_id="t", sender=sender, subject=subject, date=None, snippet=snippet)


def detect(subject: str, snippet: str = "", sender: str = "Ram Sharma <ram@abc.test>"):
    return RuleBasedDetector().detect(mail(subject, snippet, sender), TODAY)


def test_a_clear_request_with_a_deadline_becomes_a_high_priority_suggestion() -> None:
    found = detect("Contract review", "Hi, can you send me your comments by Friday? Thanks")

    assert found is not None
    assert found.title == "Reply to Ram Sharma: Contract review"
    assert found.due_date == date(2026, 10, 9)
    assert found.priority == TaskPriority.HIGH  # due within two days
    assert 0.6 <= found.confidence <= 0.95
    assert "asks you to do something" in found.reason and "Fri 09 Oct" in found.reason


def test_a_polite_request_without_a_deadline_is_medium_priority() -> None:
    found = detect("Quarterly numbers", "Please review the attached when you get a chance.")

    assert found is not None and found.due_date is None
    assert found.priority == TaskPriority.MEDIUM


@pytest.mark.parametrize("subject,snippet", [
    ("Action required: confirm your attendance", ""),
    ("Invoice #4821", "Your invoice is overdue, payment pending."),
    ("URGENT", "need your sign-off on the budget"),
])
def test_urgent_and_money_emails_are_high_priority(subject: str, snippet: str) -> None:
    found = detect(subject, snippet)

    assert found is not None and found.priority == TaskPriority.HIGH


def test_more_signals_raise_confidence() -> None:
    one = detect("Hello", "Could you look at this?")
    many = detect("Urgent: invoice overdue", "Please confirm payment by tomorrow, can you reply?")

    assert one is not None and many is not None
    assert many.confidence > one.confidence


@pytest.mark.parametrize("subject,snippet,sender", [
    ("Please confirm your order", "Click to verify", "Shop <no-reply@shop.test>"),
    ("Weekly digest", "Please read our newsletter", "News <newsletter@site.test>"),
    ("Your order has shipped", "Tracking number 123", "Ram <ram@abc.test>"),
    ("Thanks!", "Great meeting you.", "Ram <ram@abc.test>"),
    ("Lunch on Friday?", "Fancy trying the new place?", "Ram <ram@abc.test>"),
    ("Photos from the trip", "Here they are", "Sita <sita@home.test>"),
    ("Sale ends today", "Don't miss out", "Deals <marketing@store.test>"),
])
def test_ordinary_and_automated_mail_is_left_alone(subject: str, snippet: str, sender: str) -> None:
    assert detect(subject, snippet, sender) is None


def test_reply_prefixes_are_removed_and_long_titles_capped() -> None:
    found = detect("Re: RE: Fwd: Proposal draft", "please review")
    long = detect("x" * 500, "please review")

    assert found is not None and found.title == "Reply to Ram Sharma: Proposal draft"
    assert long is not None and len(long.title) == 300


def test_sender_and_subject_helpers() -> None:
    assert sender_name("Ram Sharma <ram@abc.test>") == "Ram Sharma"
    assert sender_name('"Sharma, Ram" <ram@abc.test>') == "Sharma, Ram"
    assert sender_name("ram@abc.test") == "ram@abc.test"
    assert sender_name("<ram@abc.test>") == "ram@abc.test"
    assert sender_name("") == "sender"
    assert clean_subject("Re: hi") == "hi"
    assert clean_subject("   ") == "(no subject)"


# --- Ranking tasks ----------------------------------------------------------------------------

UTC_TZ = ZoneInfo("UTC")
NOW = datetime(2026, 10, 7, 10, 0, tzinfo=UTC)


def task(title: str, *, due: datetime | None = None, priority=TaskPriority.MEDIUM, status=TaskStatus.TODO, age_days: int = 1) -> Task:
    created = NOW - timedelta(days=age_days)
    return Task(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), title=title, status=status, priority=priority,
        due_date=due, created_at=created, updated_at=created,
    )


def test_overdue_beats_due_today_beats_important_but_undated() -> None:
    tasks = [
        task("Undated urgent", priority=TaskPriority.URGENT),
        task("Due today", due=NOW.replace(hour=23, minute=59)),
        task("Overdue", due=NOW - timedelta(days=3)),
    ]

    ranked = rank_tasks(tasks, NOW, UTC_TZ)

    assert [r.task.title for r in ranked] == ["Overdue", "Due today", "Undated urgent"]


def test_reasons_explain_the_ranking() -> None:
    tasks = [
        task("A", due=NOW - timedelta(days=3), priority=TaskPriority.HIGH),
        task("B", due=NOW.replace(hour=23, minute=59)),
        task("C", due=NOW + timedelta(days=1, hours=5)),
        task("D", due=NOW + timedelta(days=3), priority=TaskPriority.URGENT),
        task("E", due=NOW - timedelta(hours=2)),
        task("F", due=NOW - timedelta(days=1), priority=TaskPriority.LOW),
    ]

    reasons = {r.task.title: r.reason for r in rank_tasks(tasks, NOW, UTC_TZ)}

    assert reasons["A"] == "Overdue by 3 days · High priority"
    assert reasons["B"] == "Due today"
    assert reasons["C"] == "Due tomorrow"
    assert reasons["D"] == "Due in 3 days · Urgent priority"
    assert reasons["E"] == "Overdue (was due earlier today)"
    assert reasons["F"] == "Overdue by 1 day"


def test_finished_and_unremarkable_tasks_are_not_flagged() -> None:
    tasks = [
        task("Done", due=NOW - timedelta(days=5), status=TaskStatus.COMPLETED),
        task("Cancelled", due=NOW - timedelta(days=5), status=TaskStatus.CANCELLED),
        task("Someday", priority=TaskPriority.LOW),
        task("Routine", priority=TaskPriority.MEDIUM),
        task("Far away", due=NOW + timedelta(days=30), priority=TaskPriority.MEDIUM),
        task("In progress medium", status=TaskStatus.IN_PROGRESS),
    ]

    assert rank_tasks(tasks, NOW, UTC_TZ) == []


def test_ties_go_to_the_earlier_deadline() -> None:
    soon = task("Soon", due=NOW.replace(hour=15), priority=TaskPriority.HIGH)
    later = task("Later", due=NOW.replace(hour=22), priority=TaskPriority.HIGH)

    assert [r.task.title for r in rank_tasks([later, soon], NOW, UTC_TZ)] == ["Soon", "Later"]


def test_due_today_follows_the_users_timezone_not_utc() -> None:
    kathmandu = ZoneInfo("Asia/Kathmandu")  # UTC+5:45
    now = datetime(2026, 10, 7, 20, 30, tzinfo=UTC)  # already 02:15 on the 8th there
    due = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)  # 17:45 on the 8th there

    in_kathmandu = rank_tasks([task("T", due=due)], now, kathmandu)[0].reason
    in_utc = rank_tasks([task("T", due=due)], now, UTC_TZ)[0].reason

    assert in_kathmandu == "Due today"
    assert in_utc == "Due tomorrow"
