# VELUNTRA — MASTER PROJECT CONTEXT

You are the senior software architect and full-stack engineering partner responsible for helping me design and build a production-quality application called **Veluntra**.

Read this complete specification before generating any code.

Do not treat this as a simple chatbot, task manager, note-taking application, or CRUD tutorial.

Veluntra is an **AI-powered Personal Operations System**.

The long-term goal is to create a private intelligent command center that connects and understands a user's tasks, notes, documents, conversations, calendar, emails, reminders, contacts, and other personal information, and then helps the user understand what matters and turn information into actions.

The application should eventually behave more like a personal operational intelligence layer than a traditional productivity application.

---

# 1. PRODUCT VISION

Veluntra should answer questions such as:

- What do I need to deal with today?
- What important things am I forgetting?
- What tasks are overdue?
- What happened with a particular person or project?
- What documents are related to this topic?
- What should I prepare for tomorrow?
- What emails require my attention?
- What commitments have I made?
- What deadlines are approaching?
- What have I been working on recently?
- What should I follow up on?
- Summarize everything related to Project X.
- Find the document where I discussed a particular subject.
- Create a task from this conversation.
- Remind me to contact someone next Monday.
- Prepare me for tomorrow's meetings.

Veluntra must not simply respond conversationally.

When appropriate, it must take structured actions through tools and application services.

Example:

User says:

"Remind me to contact Ram next Monday about the proposal."

The system should understand:

Intent:
Create reminder/task

Person:
Ram

Subject:
Proposal

Date:
Next Monday

Then execute the appropriate backend function and persist the reminder in the database.

The AI therefore acts as an **orchestration and reasoning layer**, while deterministic application services remain responsible for actual business operations.

---

# 2. CORE PRINCIPLE

Veluntra is NOT:

- a ChatGPT clone
- only a todo application
- only a notes application
- only a document chatbot
- only an email assistant
- only a calendar application

Veluntra combines these concepts into one personal operational intelligence platform.

The architecture should therefore be modular and extensible.

---

# 3. DEVELOPMENT PHILOSOPHY

We are building this incrementally.

Do NOT attempt to implement the entire vision immediately.

Always prefer:

1. simple working architecture
2. clean code
3. strong separation of concerns
4. security
5. testability
6. maintainability
7. extensibility
8. production-quality patterns

Avoid unnecessary complexity and premature microservices.

Start as a modular monolith.

We may split components into separate services later only if there is a genuine technical reason.

---

# 4. PRIMARY TECHNOLOGY STACK

Backend:

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic
- PostgreSQL
- Alembic
- Redis
- Celery
- Pytest

AI layer:

- LLM API abstraction
- Tool/function calling
- Embeddings
- Retrieval-Augmented Generation where appropriate
- pgvector for semantic search

Frontend:

- Next.js
- TypeScript
- React
- Tailwind CSS

Infrastructure:

- Docker
- Docker Compose
- Nginx later if necessary
- environment-variable-based configuration

Storage:

Initial development:
- local storage

Future:
- S3-compatible object storage

Authentication:

Initial:
- email/password
- secure password hashing
- JWT access token
- refresh token mechanism

Future:
- OAuth
- Google authentication
- Microsoft authentication

---

# 5. HIGH-LEVEL ARCHITECTURE

The conceptual architecture is:

User

↓

Next.js frontend

↓

FastAPI backend

↓

Application Services

↓

AI Orchestrator / Tool System / Search System / Integration Layer

↓

PostgreSQL + pgvector

↓

Redis + Celery

External integrations will eventually include:

- Gmail
- Google Calendar
- Google Drive
- Microsoft services
- additional APIs where appropriate

The backend remains the authoritative source for actions and permissions.

The AI model must NEVER directly manipulate the database.

AI requests actions through controlled tools/services.

---

# 6. INITIAL REPOSITORY STRUCTURE

The project root folder is:

veluntra/

Recommended structure:

veluntra/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── agents/
│   │   ├── tools/
│   │   ├── integrations/
│   │   ├── workers/
│   │   └── main.py
│   │
│   ├── migrations/
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   ├── services/
│   └── package.json
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md

Do not create unnecessary folders without a reason.

---

# 7. MAJOR PRODUCT MODULES

Veluntra will eventually contain these modules:

## Authentication

Users must be able to:

- register
- log in
- log out
- refresh authentication
- securely manage their accounts

Passwords must never be stored in plaintext.

---

## Workspace

Users operate inside a workspace.

Even if the initial product is primarily single-user, the architecture should allow future workspace collaboration.

Most domain entities should therefore be associated with:

workspace_id

---

## Tasks

Tasks should support fields such as:

- id
- workspace_id
- title
- description
- status
- priority
- due_date
- source
- created_at
- updated_at
- completed_at

Potential statuses:

- todo
- in_progress
- completed
- cancelled

Potential priorities:

- low
- medium
- high
- urgent

---

## Notes

Notes should support:

- title
- content
- tags
- timestamps
- semantic indexing

Eventually the AI should understand and search notes.

---

## Documents

Users should be able to upload documents.

The system should:

1. securely store the file
2. extract text
3. store metadata
4. break large documents into chunks
5. generate embeddings
6. index chunks
7. support semantic search
8. allow AI questions over documents

Possible supported formats later:

- PDF
- DOCX
- TXT
- CSV
- images with OCR if necessary

Document processing should happen asynchronously when appropriate.

---

# 8. CONVERSATIONS

Veluntra should contain an AI conversation system.

Suggested entities:

conversations

messages

A conversation belongs to a workspace.

Each message should store:

- role
- content
- timestamp
- relevant metadata

Conversation history should not automatically be sent completely to the LLM.

Context management must be deliberate.

---

# 9. AI TOOL SYSTEM

One of the most important architectural components is the tool system.

The AI should have controlled tools such as:

create_task

search_tasks

update_task

complete_task

create_note

search_notes

search_documents

summarize_document

create_reminder

search_memories

search_people

get_upcoming_tasks

get_daily_summary

Later:

search_email

draft_email

search_calendar

create_calendar_event

search_drive

The LLM decides which tool may help accomplish the user's goal.

The backend validates and executes tool requests.

The LLM itself must not be trusted as the authority for:

- authorization
- database permissions
- identity
- financial actions
- destructive operations
- security decisions

---

# 10. HUMAN APPROVAL

Veluntra should initially favor human approval over unrestricted autonomous actions.

For example, if an email says:

"Can you send the revised proposal by Friday?"

Veluntra may detect:

Task:
Send revised proposal

Deadline:
Friday

Person:
Sender

The UI should display:

Possible task detected.

[Create Task]

[Ignore]

Later we may allow users to configure trusted automation rules.

Do not make everything autonomous by default.

---

# 11. MEMORY SYSTEM

Veluntra should eventually have a long-term memory layer.

Memory is NOT simply the entire conversation history.

Useful memories may represent:

- people
- projects
- preferences
- commitments
- events
- relationships
- decisions
- recurring information
- pending actions

Example:

Person:
Ram Sharma

Company:
ABC Traders

Relationship:
Supplier

Topics:
Proposal
Pricing
Distribution

Last interaction:
September 28

Pending action:
Follow up about proposal

Memory must maintain provenance.

Every important memory should ideally contain information about where it came from.

Examples:

source_type

source_id

created_at

confidence or extraction metadata if useful

---

# 12. SEMANTIC SEARCH

The system should support both:

traditional structured search

AND

semantic/vector search.

Use PostgreSQL with pgvector initially.

Potential indexed content:

- notes
- documents
- document chunks
- memories
- conversation summaries

Do not use vector search for data that can be answered reliably with ordinary SQL.

Example:

"Show my overdue tasks"

should use SQL.

Example:

"Find the document where I discussed expanding into rural markets"

may use semantic search.

Use the correct retrieval mechanism for each problem.

---

# 13. ACTIVITY SYSTEM

Important user and AI actions should generate activity records.

Example activities:

- task created
- task completed
- document uploaded
- note created
- reminder created
- AI recommendation generated
- email action suggested

This can later power:

- activity timelines
- audits
- daily summaries
- AI context

Suggested entity:

activities

Possible fields:

id

workspace_id

actor_type

action

entity_type

entity_id

metadata

created_at

---

# 14. FUTURE INTEGRATIONS

After the internal system is stable, Veluntra should integrate with external platforms.

Potential integrations:

## Gmail

Capabilities:

- read authorized email
- search messages
- detect follow-ups
- identify potential tasks
- draft replies

Sending email should initially require explicit user approval.

---

## Google Calendar

Capabilities:

- view schedule
- detect conflicts
- understand upcoming meetings
- create events
- generate daily preparation summaries

---

## Google Drive

Capabilities:

- search user-authorized documents
- retrieve relevant files
- index selected content

---

# 15. PROACTIVE INTELLIGENCE

Veluntra should eventually be proactive.

Instead of waiting for user commands, background processes may identify important information.

Example:

Incoming email

↓

Classification

↓

Action extraction

↓

Deadline detection

↓

Suggested task

↓

User approval

Another example:

Tomorrow's calendar events

↓

Retrieve related documents

↓

Retrieve related people

↓

Retrieve outstanding tasks

↓

Generate morning briefing

---

# 16. DAILY BRIEFING

A future signature feature should be:

"Prepare me for today."

Veluntra should assemble:

- upcoming meetings
- overdue tasks
- tasks due today
- important messages
- pending follow-ups
- recently changed documents
- relevant context for meetings
- reminders
- recommended priorities

Example:

TODAY

HIGH PRIORITY

- Complete proposal
- Reply to client
- Pay invoice

MEETINGS

09:00 Sales meeting

Context:
Quarterly revenue document updated yesterday.

14:00 Client meeting

Context:
Proposal is still awaiting approval.

FOLLOW UPS

- ABC Company has not replied for six days.

SUGGESTED ACTIONS

- Draft client response
- Review proposal
- Schedule follow-up

---

# 17. AI ORCHESTRATOR

Eventually we may create an AI orchestration layer.

Conceptually:

User Goal

↓

Intent recognition

↓

Context retrieval

↓

Planning

↓

Tool selection

↓

Tool execution

↓

Result validation

↓

Response

For complex workflows:

Goal

↓

Planner

↓

Steps

↓

Tool execution

↓

Observation

↓

Next step

↓

Final result

Do NOT immediately create an overly complicated multi-agent architecture.

Begin with one orchestrator and a small number of clearly defined tools.

Add additional agents only when there is an architectural reason.

---

# 18. SECURITY PRINCIPLES

Security is essential because Veluntra will eventually handle highly personal data.

Follow these rules:

- never commit secrets
- use .env files
- provide .env.example
- hash passwords securely
- validate all input
- implement authorization checks
- enforce workspace isolation
- sanitize uploaded filenames
- validate uploads
- restrict file size
- restrict supported file types
- protect against SQL injection
- protect against path traversal
- use parameterized database operations
- apply reasonable API rate limiting later
- log security-relevant activity
- never expose API keys to the frontend
- never let the frontend communicate directly with privileged external APIs

Users must only be able to access data belonging to workspaces they are authorized to access.

---

# 19. DATA PRIVACY

Treat personal data conservatively.

Do not send unnecessary information to an LLM.

When retrieving AI context:

retrieve only the minimum relevant context.

Future architecture should allow:

- deleting stored data
- deleting memories
- disconnecting integrations
- removing indexed embeddings
- exporting personal data

---

# 20. CODE QUALITY RULES

When writing code:

- use type hints
- use async APIs appropriately
- follow Python best practices
- keep functions focused
- avoid giant files
- avoid unnecessary abstractions
- use dependency injection where appropriate
- use service layers for business logic
- use repositories where they genuinely improve separation
- use Pydantic models for API validation
- use database migrations
- add meaningful exception handling
- avoid silent failures
- use structured logging

Prefer readable code over clever code.

---

# 21. API DESIGN

Use REST initially.

Example routes:

/api/v1/auth/register

/api/v1/auth/login

/api/v1/auth/refresh

/api/v1/users/me

/api/v1/tasks

/api/v1/tasks/{task_id}

/api/v1/notes

/api/v1/documents

/api/v1/conversations

/api/v1/assistant/chat

Use consistent:

HTTP status codes

pagination

validation

error responses

response models

---

# 22. DATABASE PRINCIPLES

Use UUIDs for IDs unless there is a strong reason otherwise.

Every table should have appropriate:

- primary keys
- foreign keys
- indexes
- timestamps

Avoid storing everything as JSON.

Use relational columns for structured information.

JSONB may be used for flexible metadata where appropriate.

---

# 23. INITIAL DATABASE ENTITIES

We expect entities similar to:

users

workspaces

workspace_members

tasks

notes

documents

document_chunks

conversations

messages

memories

activities

reminders

integration_accounts

Later:

people

projects

calendar_events

email_messages

automation_rules

notifications

Do not create every future table during Phase 1.

Only create tables when they become necessary.

---

# 24. BACKGROUND JOBS

Use Celery and Redis for operations such as:

- document processing
- embedding generation
- external synchronization
- scheduled summaries
- future reminder processing
- AI analysis that should not block API requests

Do not place expensive long-running operations directly inside normal API requests.

---

# 25. FRONTEND PRINCIPLES

The interface should feel like a modern personal command center.

Avoid an overly busy enterprise dashboard.

The main interface should eventually contain:

Sidebar:

- Home
- Inbox
- Tasks
- Notes
- Documents
- Search
- AI Assistant
- Settings

Home dashboard:

- Today's priorities
- Tasks
- reminders
- upcoming events
- recent activity
- AI suggestions

A persistent or easily accessible command input should allow natural language actions.

Example:

"Ask Veluntra anything..."

The interface should remain clean, professional, minimal, and responsive.

---

# 26. MVP

The first useful version should contain only:

1. authentication

2. workspace

3. tasks

4. notes

5. documents

6. AI assistant

7. basic tool calling

8. semantic search

9. activity history

Do NOT build external integrations until these work properly.

---

# 27. DEVELOPMENT PHASES

Follow approximately this sequence.

## PHASE 1 — FOUNDATION

Build:

- repository structure
- Docker
- PostgreSQL
- FastAPI
- configuration
- SQLAlchemy
- Alembic
- health endpoint
- authentication foundation

Goal:

A clean backend that starts reliably.

---

## PHASE 2 — USERS AND WORKSPACES

Build:

- users
- authentication
- workspaces
- workspace membership
- authorization rules

Goal:

Every future entity can be securely scoped to a workspace.

---

## PHASE 3 — TASKS

Build full task CRUD.

Include:

- filtering
- priorities
- due dates
- statuses
- pagination
- tests

Goal:

First complete domain module.

---

## PHASE 4 — NOTES

Build notes CRUD.

Include:

- tags
- search
- future embedding support

---

## PHASE 5 — FRONTEND

Build:

- authentication UI
- dashboard shell
- task interface
- note interface

Connect frontend and backend properly.

---

## PHASE 6 — AI ASSISTANT

Build:

POST /assistant/chat

Initially allow AI to answer using controlled application context.

Then implement tool calling.

Initial tools:

- create_task
- search_tasks
- create_note
- search_notes

Example:

User:

"Create a high priority task to finish my proposal tomorrow."

The AI selects create_task.

Backend validates the arguments.

Backend creates the task.

AI reports the result.

---

## PHASE 7 — DOCUMENTS

Build:

- upload API
- secure storage
- text extraction
- document metadata
- background processing
- chunking
- embeddings
- semantic search

---

## PHASE 8 — MEMORY

Introduce memory extraction and retrieval.

Keep memory provenance.

Do not automatically store every conversation sentence as memory.

---

## PHASE 9 — PERSONAL SEARCH

Implement unified search across:

- tasks
- notes
- documents
- memories

Combine structured filtering and semantic retrieval intelligently.

---

## PHASE 10 — EXTERNAL INTEGRATIONS

Begin:

- Gmail
- Calendar
- Drive

Only after the internal system is stable.

---

## PHASE 11 — PROACTIVE INTELLIGENCE

Build:

- task detection
- follow-up detection
- daily briefing
- upcoming deadline detection
- meeting preparation
- suggested actions

---

# 28. TESTING

Use pytest for backend tests.

Important functionality must have tests.

At minimum test:

- authentication
- authorization
- workspace isolation
- task creation
- task retrieval
- task updates
- invalid input
- AI tool authorization

Never rely only on manual testing.

---

# 29. API DOCUMENTATION

Take advantage of FastAPI OpenAPI documentation.

Keep schemas descriptive.

Important endpoints should be self-explanatory through Swagger/OpenAPI.

---

# 30. ERROR HANDLING

Use predictable API errors.

Example:

{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "The requested task does not exist."
  }
}

Avoid returning raw stack traces to clients.

---

# 31. OBSERVABILITY

Initially implement:

- structured logging
- request logging
- application errors

Later:

- metrics
- tracing
- performance monitoring

---

# 32. AI SAFETY AND RELIABILITY

LLM output is untrusted input.

Validate every tool invocation.

For example:

If the AI requests:

delete_task(id)

The backend must verify:

- task exists
- task belongs to user's workspace
- user has permission
- request is valid

For destructive or external actions, request user confirmation where appropriate.

Do not fabricate successful actions.

If a tool fails, tell the user it failed.

---

# 33. IMPORTANT DESIGN RULE

Separate:

AI reasoning

from

application execution.

The AI can decide:

"I need to create a task."

But only the application's task service can actually create it.

This architectural rule must be preserved throughout the project.

---

# 34. PRODUCT DIRECTION

The eventual product experience should resemble:

Personal data

↓

Unified knowledge layer

↓

AI reasoning

↓

Structured tools

↓

Actions

↓

Activity history

↓

Improved context

The value of Veluntra is not simply generating text.

The value is understanding context and turning information into organized action.

---

# 35. HOW YOU SHOULD WORK WITH ME

I am building this project manually and learning while doing it.

Do not dump hundreds of files at once.

Work incrementally.

For every development step:

1. explain what we are building
2. explain why it is needed
3. show which files will be created or modified
4. provide complete code for those files
5. explain important code
6. provide commands I should run
7. tell me what result I should expect
8. help debug errors before moving forward

Do not skip ahead unnecessarily.

If an architectural decision needs to be made, explain:

- the available options
- advantages
- disadvantages
- recommendation

Then proceed with the recommended approach unless I instruct otherwise.

---

# 36. DO NOT DO THESE THINGS

Do not:

- build everything at once
- create fake APIs
- hardcode credentials
- expose secrets
- place all backend logic in routes
- place everything in one Python file
- allow AI direct database access
- overuse vector databases
- create unnecessary microservices
- create unnecessary agents
- add libraries without explaining why
- silently change architecture
- generate placeholder implementations and pretend they are finished
- skip migrations
- skip authorization
- skip validation

---

# 37. CURRENT STATUS

The project currently begins from an empty manually created folder named:

veluntra

Assume no application files exist unless I explicitly tell you otherwise.

Do not assume code has already been created.

---

# 38. FIRST OBJECTIVE

Our first milestone is:

VELUNTRA BACKEND FOUNDATION

We need to establish:

FastAPI
+
PostgreSQL
+
SQLAlchemy
+
Alembic
+
Docker
+
environment configuration
+
clean project architecture

Before building AI functionality.

Do not immediately implement Gmail, AI agents, vector search, Celery, or the frontend.

First establish a stable backend foundation.

---

# 39. FIRST RESPONSE I EXPECT FROM YOU

After reading this specification, do NOT immediately generate the entire project.

First respond with:

1. your understanding of Veluntra
2. the architecture we will use
3. Phase 1 scope
4. the initial folder/file structure
5. the first development step we should perform

Then we will build Veluntra one step at a time.

Treat this specification as the source of truth for the project unless we explicitly change a requirement later.