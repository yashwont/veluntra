"""Fill a demo account with sample data, so a fresh install has something to look at.

    docker compose exec backend python -m scripts.seed_demo          # create it
    docker compose exec backend python -m scripts.seed_demo --reset  # wipe and recreate

Signs in as  demo@veluntra.dev  /  demo-password-123  (local demo only: change nothing
here for anything public). Safe to run twice: it does nothing if the account exists.
Everything goes through the same services the API uses, so the data is exactly what a
real user would create, including the assistant conversation and the memory it saved.
"""

import asyncio
import sys
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, text

from app.db.session import SessionLocal, engine
from app.llm.fake import FakeProvider
from app.models.user import User
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.memory import MemoryCreate
from app.schemas.note import NoteCreate
from app.schemas.task import TaskCreate
from app.services.assistant_service import AssistantService
from app.services.auth_service import AuthService
from app.services.document_processing import process_document
from app.services.document_service import DocumentService
from app.services.memory_service import MANUAL_SOURCE, MemoryService
from app.services.note_service import NoteService
from app.services.task_service import TaskService

DEMO_EMAIL = "demo@veluntra.dev"
DEMO_PASSWORD = "demo-password-123"
DEMO_NAME = "Demo User"

NOTES = [
    ("ABC Traders proposal", ["clients", "proposal"],
     "Proposal for ABC Traders: volume pricing from 500 units, net 30 payment terms, delivery within two weeks. "
     "Ram wants the revised pricing before their board meeting next week."),
    ("Weekly review template", ["productivity"],
     "1. What got done this week?\n2. What slipped, and why?\n3. Top three priorities for next week.\n4. Anything to follow up on?"),
    ("Ideas for the mobile app", ["product", "ideas"],
     "Offline mode for notes, a share sheet to capture links, push reminders for tasks due today, widget for the daily briefing."),
    ("Sales standup notes", ["meetings", "sales"],
     "Pipeline is healthy. Two proposals out (ABC Traders, Himal Foods). Need pricing sheet finalised and a follow-up with Anita about the partnership."),
]

DOCUMENTS = [
    ("Quarterly revenue review.txt", """Quarterly revenue review

Revenue grew 12 percent quarter over quarter, driven by the sales segment and two new distribution partners.

Key numbers: recurring revenue is up 9 percent, new customers up 14 percent, churn steady at 2 percent.

Risks: supplier contract delays could affect delivery dates, and the pricing change planned for November needs customer communication.

Next steps: finalise the pricing sheet, review the hiring plan, and prepare the board summary."""),
    ("ABC Traders contract summary.txt", """ABC Traders supply contract summary

Term: 12 months from signing, renewable. Standard tier 120 per unit; volume tier 95 per unit above 500 units.

Payment terms: net 30. Late payments accrue 1.5 percent monthly. Either party may terminate with 60 days notice.

Contact: Ram Sharma, procurement. Prefers email over phone calls."""),
    ("Hiring plan 2026.md", """# Hiring plan 2026

## Engineering
Two backend engineers and one frontend engineer by the end of Q4. Priority is the mobile app launch in November.

## Operations
One operations coordinator to take over supplier follow-ups and invoicing.

## Budget
Approved headcount budget covers three hires; a fourth needs board approval."""),
]

MEMORIES = [
    ("Prefers meetings in the morning and no calls after 5pm", "preference", None),
    ("Promised Priya the revised quarterly agenda before the review", "commitment", "Priya Nair"),
    ("Decided to offer ABC Traders the volume pricing tier", "decision", "ABC Traders"),
    ("Mobile app launch is targeted for November", "project", "Mobile app"),
]

CHAT = [
    "Remember that Ram Sharma is the contact at ABC Traders and prefers email over calls",
    "Create a high priority task to send revised pricing to Ram by Friday",
    "Search notes for proposal",
]


def end_of_day(days: int) -> datetime:
    day = (datetime.now(UTC) + timedelta(days=days)).date()
    return datetime.combine(day, time(23, 59, 59), tzinfo=UTC)


async def reset(session) -> None:
    user = await UserRepository(session).get_by_email(DEMO_EMAIL)
    if user is None:
        return
    for workspace, _ in await WorkspaceRepository(session).list_for_user(user.id):
        await session.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": workspace.id})
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
    print("Removed the existing demo account.")


async def seed() -> None:
    async with SessionLocal() as session:
        if "--reset" in sys.argv:
            await reset(session)
        if await UserRepository(session).get_by_email(DEMO_EMAIL) is not None:
            print(f"Demo account already exists: {DEMO_EMAIL} / {DEMO_PASSWORD}  (use --reset to recreate)")
            return

        user = await AuthService(session).register(DEMO_EMAIL, DEMO_PASSWORD, DEMO_NAME)
        [(workspace, _)] = await WorkspaceRepository(session).list_for_user(user.id)
        ws = workspace.id

        # The assistant conversation first: the memory and task it creates carry real provenance
        assistant = AssistantService(session, user, ws, FakeProvider())
        conversation_id = None
        for message in CHAT:
            conversation, _reply = await assistant.chat(message, conversation_id, "UTC")
            conversation_id = conversation.id

        tasks = TaskService(session, ws)
        stale = await tasks.create(TaskCreate(title="Review hiring plan", priority="medium", status="in_progress"))
        for title, priority, due, status in [
            ("Pay cloud hosting invoice 1042", "high", end_of_day(-2), "todo"),
            ("Follow up with Anita about the partnership", "medium", end_of_day(0), "todo"),
            ("Prepare slides for the quarterly revenue review", "medium", end_of_day(1), "todo"),
            ("Renew the company domain name", "urgent", end_of_day(5), "todo"),
            ("Book dentist appointment", "low", None, "todo"),
            ("Draft Q3 goals", "medium", None, "completed"),
        ]:
            await tasks.create(TaskCreate(title=title, priority=priority, due_date=due, status=status))
        # Make one task look neglected so the briefing has a follow-up to show
        await session.execute(
            text("UPDATE tasks SET updated_at = now() - interval '9 days' WHERE id = :id"),
            {"id": stale.id},
        )
        await session.commit()

        notes = NoteService(session, ws)
        for title, tags, content in NOTES:
            await notes.create(NoteCreate(title=title, content=content, tags=tags))

        documents = DocumentService(session, ws)
        for filename, content in DOCUMENTS:
            document = await documents.upload(filename=filename, data=content.encode(), user_id=user.id)
            await process_document(document.id)  # extract, chunk and embed right now

        memories = MemoryService(session, ws)
        for content, kind, subject in MEMORIES:
            await memories.create(MemoryCreate(content=content, kind=kind, subject=subject), MANUAL_SOURCE)

        print("Demo account created.")
        print(f"  Email:    {DEMO_EMAIL}")
        print(f"  Password: {DEMO_PASSWORD}")
        print("  Open http://localhost:3000 and sign in. With GOOGLE_PROVIDER=demo, Connections > Connect Google")
        print("  adds a sample calendar, inbox and Drive.")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
