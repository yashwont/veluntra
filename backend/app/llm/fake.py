"""A rule-based stand-in for a real model, so the whole assistant (UI, tools,
persistence, tests) works without an API key.

It is NOT intelligent: it recognises a handful of phrasings with regular
expressions and emits tool calls the way a real model would. Anything else gets a
help message. It exists to exercise the real pipeline, not to simulate a model.
"""

import json
import re
import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.llm.types import (
    AssistantToolTurn,
    LLMResponse,
    LLMTurn,
    TextTurn,
    ToolCall,
    ToolDefinition,
    ToolResultsTurn,
)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PRIORITIES = ("urgent", "high", "medium", "low")

HELP = (
    "I'm running in demo mode (no AI model is connected), so I only understand a few "
    "phrasings. Try:\n"
    "- \"Create a high priority task to finish my proposal tomorrow\"\n"
    "- \"Remind me to call Ram next Monday\"\n"
    "- \"What are my overdue tasks?\"\n"
    "- \"Create a note called Ideas saying try a weekly review\"\n"
    "- \"Search notes for proposal\"\n"
    "- \"Remember that Ram prefers email over calls\"\n"
    "- \"What do you remember about Ram?\"\n"
    "- \"Search everything for proposal\"\n"
    "- \"What is on my calendar this week?\"\n"
    "- \"Search my email for invoice\"\n"
    "- \"Search my drive for budget\"\n"
    "- \"Prepare me for today\""
)


def _today(system: str) -> date:
    match = re.search(r"Current date: (\d{4}-\d{2}-\d{2})", system)
    return date.fromisoformat(match.group(1)) if match else date.today()


def _priority(text: str) -> str | None:
    match = re.search(r"\b(urgent|high|medium|low)[- ]priority\b|\bpriority[: ]+(urgent|high|medium|low)\b", text)
    return (match.group(1) or match.group(2)) if match else None


_DUE_PATTERN = re.compile(
    r"\b(?:by |on |for |due )?(today|tomorrow|(?:next |this |on )?(" + "|".join(WEEKDAYS) + r")|in (\d+) days?)\b",
    re.IGNORECASE,
)


def _due(text: str, today: date) -> date | None:
    match = _DUE_PATTERN.search(text)
    if not match:
        return None
    word = match.group(1).lower()
    weekday = match.group(2).lower() if match.group(2) else None
    days = match.group(3)
    if word == "today":
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    if days:
        return today + timedelta(days=int(days))
    ahead = (WEEKDAYS.index(weekday) - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def _clean_title(text: str) -> str:
    text = _DUE_PATTERN.sub("", text)
    text = re.sub(
        r"\b(urgent|high|medium|low)[- ]priority\b|\bpriority[: ]+(urgent|high|medium|low)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" .,:;!-")
    return text[:1].upper() + text[1:]


class FakeProvider:
    name = "fake"

    async def generate(
        self,
        *,
        system: str,
        turns: Sequence[LLMTurn],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        last = turns[-1]
        if isinstance(last, ToolResultsTurn):
            return LLMResponse(text=self._summarize(turns, last))
        assert isinstance(last, TextTurn)
        call = self._plan(last.text, _today(system))
        if call is None:
            return LLMResponse(text=HELP)
        return LLMResponse(tool_calls=[call], stop_reason="tool_use")

    # --- intent -> tool call ---------------------------------------------------

    def _plan(self, text: str, today: date) -> ToolCall | None:
        lowered = text.lower().strip()

        everywhere = re.match(
            r"(?:search|find|look for)\s+(?:everywhere|everything|all my \w+|anywhere)\s+(?:for|about)\s+(.+)$",
            text.strip(),
            re.I,
        )
        if everywhere:
            return self._call("search_everything", {"query": everywhere.group(1).strip(" ?.!\"'")})
        if not re.search(r"\bremind me\b|\btask\b|\bnote\b|\bremember\b", lowered) and re.search(
            r"\bprepare me\b|\bdaily briefing\b|\bbriefing\b|\bwhat should i (?:focus|work) on\b|\bplan my day\b",
            lowered,
        ):
            return self._call("get_briefing", {})
        # Looking things up in Google: but "remind me to email Ram" is still a task
        lookup = not re.search(r"\bremind me\b|\btask\b|\bnote\b|\bremember\b", lowered)
        if lookup and re.search(r"\b(calendar|schedule|meetings?|agenda)\b", lowered):
            days = 1 if re.search(r"\btoday\b", lowered) else 7 if re.search(r"\bweek\b", lowered) else 3
            return self._call("get_calendar", {"days": days})
        if lookup and re.search(r"\b(e-?mails?|inbox|gmail)\b", lowered):
            about = re.search(r"\b(?:for|about|from)\s+(.+)$", text, re.I)
            query = about.group(1).strip(" ?.!\"'") if about else ""
            return self._call("search_email", {"query": query})
        if lookup and re.search(r"\bdrive\b", lowered):
            about = re.search(r"\b(?:for|about)\s+(.+)$", text, re.I)
            query = about.group(1).strip(" ?.!\"'") if about else ""
            return self._call("search_drive", {"query": query})
        remember = re.match(r"(?:please )?remember(?: that)?[:,]?\s+(.+)$", text.strip(), re.I)
        if remember:
            return self._remember(remember.group(1))
        if re.search(r"\bremember\b|\bknow about\b", lowered):
            about = re.search(r"\b(?:about|of|regarding)\s+(.+)$", text, re.I)
            query = about.group(1).strip(" ?.!\"'") if about else ""
            return self._call("search_memories", {"query": query or "the user"})
        if re.search(r"\b(create|add|write|make|new)\b.*\bnote\b", lowered):
            return self._create_note(text)
        if re.search(r"\b(search|find|look)\b.*\bnotes?\b", lowered):
            query = re.search(r"\b(?:about|for|containing|on|mentioning)\s+(.+)$", text, re.I)
            args: dict[str, Any] = {"query": query.group(1).strip(" ?.!\"'")} if query else {}
            return self._call("search_notes", args)
        if re.search(r"\b(create|add|make|new)\b.*\btask\b|\bremind me to\b|\btask to\b", lowered):
            return self._create_task(text, today)
        if re.search(r"\btasks?\b|\bto-?dos?\b", lowered):
            return self._search_tasks(lowered, today)
        return None

    def _remember(self, statement: str) -> ToolCall:
        lowered = statement.lower()
        kind = "fact"
        if re.search(r"\b(prefer|prefers|likes?|loves?|hates?|dislikes?)\b", lowered):
            kind = "preference"
        elif re.search(r"\b(decided|decision|we will|i will go with)\b", lowered):
            kind = "decision"
        elif re.search(r"\b(promised|committed|owe|will send|deadline)\b", lowered):
            kind = "commitment"
        args: dict[str, Any] = {"content": statement.strip(" .!")[:1000], "kind": kind}
        subject = re.match(r"([A-Z][\w'-]+(?: [A-Z][\w'-]+)*)\b", statement.strip())
        if subject:
            args["subject"] = subject.group(1)
        return self._call("remember", args)

    def _create_task(self, text: str, today: date) -> ToolCall:
        remind = re.search(r"\bremind me to\s+(.+)$", text, re.I)
        explicit = re.search(r"\btask\s+(?:to|called|titled|named|:)\s*(.+)$", text, re.I)
        match = remind or explicit
        raw = match.group(1) if match else re.split(r"\btask\b", text, maxsplit=1, flags=re.I)[-1]
        args: dict[str, Any] = {"title": _clean_title(raw) or "New task"}
        if (priority := _priority(text.lower())):
            args["priority"] = priority
        if (due := _due(text.lower(), today)):
            args["due_date"] = due.isoformat()
        return self._call("create_task", args)

    def _create_note(self, text: str) -> ToolCall:
        title_match = re.search(r"\b(?:called|titled|named)\s+\"?(.+?)\"?(?=\s+(?:saying|with|that says|content)\b|:|$)", text, re.I)
        content_match = re.search(r"\b(?:saying|that says|with content|content)\s*:?\s*(.+)$|:\s*(.+)$", text, re.I)
        title = title_match.group(1).strip() if title_match else "Note"
        content = ""
        if content_match:
            content = (content_match.group(1) or content_match.group(2) or "").strip()
        return self._call("create_note", {"title": title[:300], "content": content})

    def _search_tasks(self, lowered: str, today: date) -> ToolCall:
        args: dict[str, Any] = {}
        if "overdue" in lowered:
            args["overdue"] = True
        elif re.search(r"\b(completed|done|finished)\b", lowered):
            args["status"] = "completed"
        elif "in progress" in lowered:
            args["status"] = "in_progress"
        if (priority := _priority(lowered) or next((p for p in PRIORITIES if re.search(rf"\b{p}\b", lowered)), None)):
            args["priority"] = priority
        if "this week" in lowered or "upcoming" in lowered:
            args["due_after"] = today.isoformat()
            args["due_before"] = (today + timedelta(days=7)).isoformat()
        return self._call("search_tasks", args)

    @staticmethod
    def _call(name: str, args: dict[str, Any]) -> ToolCall:
        return ToolCall(id=f"fake_{uuid.uuid4().hex[:12]}", name=name, input=args)

    @staticmethod
    def _briefing_text(b: dict[str, Any]) -> str:
        parts = [f"Your day, {b['date']}:"]
        if b["priorities"]:
            parts.append("Top priorities:\n" + "\n".join(f"- {p['title']} ({p['why']})" for p in b["priorities"]))
        if b["due_today"]:
            parts.append("Due today:\n" + "\n".join(f"- {t}" for t in b["due_today"]))
        if b["meetings"]:
            parts.append("Meetings:\n" + "\n".join(f"- {m['start']} {m['title']}" for m in b["meetings"]))
        elif b["meetings_unavailable"]:
            parts.append("I can't see your calendar (Google isn't connected).")
        if b["follow_ups"]:
            parts.append("Follow-ups:\n" + "\n".join(f"- {f}" for f in b["follow_ups"]))
        if b["suggested_actions"]:
            parts.append("Suggested next steps:\n" + "\n".join(f"- {a}" for a in b["suggested_actions"]))
        if len(parts) == 1:
            parts.append("Nothing pressing: no overdue or due tasks and nothing scheduled.")
        return "\n\n".join(parts)

    # --- tool results -> reply -----------------------------------------------------

    def _summarize(self, turns: Sequence[LLMTurn], results: ToolResultsTurn) -> str:
        names = {}
        for turn in turns:
            if isinstance(turn, AssistantToolTurn):
                names.update({c.id: c.name for c in turn.tool_calls})

        lines: list[str] = []
        for result in results.results:
            payload = json.loads(result.content)
            name = names.get(result.tool_call_id, "the tool")
            if not payload.get("ok"):
                lines.append(f"I couldn't do that: {payload.get('error', 'the action failed')}")
            elif name == "create_task":
                task = payload["task"]
                extras = [task["priority"] + " priority"] + ([f"due {task['due_date']}"] if task["due_date"] else [])
                lines.append(f"Done. I created the task “{task['title']}” ({', '.join(extras)}).")
            elif name == "create_note":
                lines.append(f"Done. I saved the note “{payload['note']['title']}”.")
            elif name == "search_tasks":
                found = payload["tasks"]
                if not found:
                    lines.append("You have no matching tasks.")
                else:
                    shown = "\n".join(
                        f"- {t['title']} ({t['priority']}, {t['status'].replace('_', ' ')}"
                        + (f", due {t['due_date']}" if t["due_date"] else "")
                        + ")"
                        for t in found
                    )
                    lines.append(f"I found {payload['total']} matching task(s):\n{shown}")
            elif name == "remember":
                memory = payload["memory"]
                if payload["already_known"]:
                    lines.append(f"I already knew that: “{memory['content']}”.")
                else:
                    lines.append(f"Got it. I'll remember: “{memory['content']}”.")
            elif name == "search_memories":
                found = payload["memories"]
                if not found:
                    lines.append("I don't remember anything about that yet.")
                else:
                    shown = "\n".join(f"- {m['content']}" for m in found)
                    lines.append(f"Here is what I remember:\n{shown}")
            elif name == "search_everything":
                found = payload["results"]
                if not found:
                    lines.append("I found nothing matching that anywhere.")
                else:
                    shown = "\n".join(f"- [{r['type']}] {r['title']}" for r in found)
                    lines.append(f"I found {len(found)} result(s):\n{shown}")
            elif name == "get_briefing":
                lines.append(self._briefing_text(payload))
            elif name == "get_calendar":
                events = payload["events"]
                if not events:
                    lines.append("Your calendar is clear for that period.")
                else:
                    shown = "\n".join(f"- {e['start'][:16].replace('T', ' ')}  {e['title']}" for e in events)
                    clash = (
                        "\nHeads up, these overlap: "
                        + "; ".join(" and ".join(c["between"]) for c in payload["conflicts"])
                        if payload["conflicts"]
                        else ""
                    )
                    lines.append(f"Here is your schedule:\n{shown}{clash}")
            elif name == "search_email":
                found = payload["emails"]
                if not found:
                    lines.append("I found no matching emails.")
                else:
                    shown = "\n".join(f"- {e['subject']} (from {e['from']})" for e in found)
                    lines.append(f"I found {len(found)} email(s):\n{shown}")
            elif name == "search_drive":
                found = payload["files"]
                if not found:
                    lines.append("I found no matching Drive files.")
                else:
                    shown = "\n".join(f"- {f['name']}" for f in found)
                    lines.append(f"I found {len(found)} file(s) in Drive:\n{shown}")
            elif name == "search_notes":
                found = payload["notes"]
                if not found:
                    lines.append("I found no matching notes.")
                else:
                    shown = "\n".join(f"- {n['title']}" for n in found)
                    lines.append(f"I found {payload['total']} matching note(s):\n{shown}")
        return "\n".join(lines) or "Done."
