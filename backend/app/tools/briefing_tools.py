from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.briefing_service import BriefingService
from app.tools.base import Tool, ToolContext


class GetBriefingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def get_briefing(ctx: ToolContext, args: GetBriefingInput) -> dict[str, Any]:
    b = await BriefingService(
        ctx.session, ctx.workspace_id, ctx.user_id, ctx.google, ctx.timezone
    ).build()

    def titles(items) -> list[str]:
        return [i.title for i in items]

    return {
        "date": b.date.isoformat(),
        "priorities": [{"title": p.title, "why": p.reason} for p in b.priorities],
        "overdue": titles(b.overdue),
        "due_today": titles(b.due_today),
        "due_tomorrow": titles(b.due_tomorrow),
        "meetings": [
            {
                "title": m.title,
                "start": m.start.astimezone(ctx.timezone).strftime("%H:%M") if not m.all_day else "all day",
                "overlaps_another": m.overlaps,
                "related": [f"{c.type}: {c.title}" for c in m.context],
            }
            for m in b.meetings
        ],
        "meetings_unavailable": None if b.meetings_status == "ok" else b.meetings_status,
        "follow_ups": [f"{f.title}: {f.detail} ({f.days_waiting}d)" for f in b.follow_ups],
        "recent_documents": [d.filename for d in b.recent_documents],
        "suggested_tasks_waiting": b.pending_suggestions,
        "suggested_actions": b.suggested_actions,
    }


BRIEFING_TOOLS = [
    Tool(
        name="get_briefing",
        description=(
            "Prepare the user's day: what to do first and why, overdue and due tasks, today's "
            "meetings with related documents and notes, follow-ups and suggested next steps. "
            "Use it for 'prepare me for today', 'what should I focus on' or 'what's my day like'."
        ),
        input_model=GetBriefingInput,
        handler=get_briefing,
    ),
]
