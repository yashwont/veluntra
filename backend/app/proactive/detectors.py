"""Spotting emails that ask the user to do something.

This is a heuristic, not understanding: it looks for the wording people use when they
want something done ("please send", "can you", "deadline", "invoice due"). It errs
towards staying quiet, and everything it finds is only a *suggestion* the user must
accept. The `ActionDetector` interface exists so a language model can replace it
later without touching anything that uses it.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from app.integrations.google.types import EmailSummary
from app.models.task import TaskPriority
from app.proactive.dates import find_deadline

MIN_CONFIDENCE = 0.6
MAX_TITLE = 300

# Automated mail rarely needs a human reply: never suggest tasks from it
_AUTOMATED_SENDER = re.compile(
    r"no-?reply|do-?not-?reply|notifications?@|newsletter|mailer-daemon|updates@|marketing@|"
    r"@.*\.(?:mailchimp|sendgrid|substack)\.",
    re.IGNORECASE,
)
_PREFIX = re.compile(r"^\s*(?:(?:re|fwd?|fw)\s*:\s*)+", re.IGNORECASE)

_ACTION_VERBS = (
    r"send|review|confirm|approve|sign|reply|respond|submit|share|update|complete|pay|prepare|"
    r"check|call|schedule|provide|forward|finalize|finalise|look|let me know|get back"
)
# (pattern, confidence). A message matching several gets a small boost.
_SIGNALS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(action (?:required|needed)|response required|urgent|asap|time[- ]sensitive)\b", re.I), 0.75),
    (re.compile(rf"\b(please|kindly)\b[^.?!]*\b(?:{_ACTION_VERBS})\b", re.I), 0.7),
    (re.compile(r"\b(?:can|could|would|will) you\b", re.I), 0.65),
    (re.compile(r"\bi(?:'d| would) (?:appreciate|like) (?:it )?if you\b|\bneed (?:you to|your)\b", re.I), 0.65),
    (re.compile(r"\b(?:invoice|payment|bill)\b[^.?!]*\b(?:due|overdue|outstanding|pending)\b|\b(?:due|overdue|outstanding)\b[^.?!]*\b(?:invoice|payment|bill)\b", re.I), 0.7),
    (re.compile(r"\bdeadline\b|\bdue (?:on|by|date)\b|\bby (?:eod|end of (?:the )?day|tomorrow|today|next week|monday|tuesday|wednesday|thursday|friday)\b", re.I), 0.6),
    (re.compile(r"\b(?:friendly )?reminder\b|\bfollowing up\b|\bfollow[- ]up\b|\bany update\b", re.I), 0.6),
]
_URGENT = re.compile(r"\b(urgent|asap|immediately|time[- ]sensitive|action required)\b", re.I)
_MONEY = re.compile(r"\b(invoice|payment|bill)\b", re.I)


@dataclass(frozen=True)
class ActionCandidate:
    title: str
    description: str
    priority: TaskPriority
    due_date: date | None
    confidence: float
    reason: str


class ActionDetector(Protocol):
    def detect(self, email: EmailSummary, today: date) -> ActionCandidate | None: ...


def sender_name(sender: str) -> str:
    """"Ram Sharma <ram@abc.test>" -> "Ram Sharma"; with no display name, the address."""
    name = re.sub(r"<[^>]*>", "", sender).strip().strip('"').strip()
    return name or sender.strip("<> ") or "sender"


def clean_subject(subject: str) -> str:
    return _PREFIX.sub("", subject).strip() or "(no subject)"


class RuleBasedDetector:
    def detect(self, email: EmailSummary, today: date) -> ActionCandidate | None:
        if _AUTOMATED_SENDER.search(email.sender):
            return None
        text = f"{email.subject}\n{email.snippet}"
        hits = [confidence for pattern, confidence in _SIGNALS if pattern.search(text)]
        if not hits:
            return None
        confidence = min(0.95, max(hits) + 0.05 * (len(hits) - 1))
        if confidence < MIN_CONFIDENCE:
            return None

        due = find_deadline(text, today)
        urgent = bool(_URGENT.search(text)) or (due is not None and due <= today + timedelta(days=2))
        priority = TaskPriority.HIGH if urgent or _MONEY.search(text) else TaskPriority.MEDIUM
        who, subject = sender_name(email.sender), clean_subject(email.subject)
        reasons = ["asks you to do something" if confidence >= 0.65 else "mentions something to follow up"]
        if due:
            reasons.append(f"mentions {due.strftime('%a %d %b')}")
        return ActionCandidate(
            title=f"Reply to {who}: {subject}"[:MAX_TITLE],
            description=f"From {who}: {email.snippet.strip()}"[:2000],
            priority=priority,
            due_date=due,
            confidence=round(confidence, 2),
            reason=f"The email {' and '.join(reasons)}.",
        )
