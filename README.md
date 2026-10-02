# Veluntra

An AI-powered personal operations system: tasks, notes, documents and conversations in one private command center, with an AI layer that acts only through validated backend services.

The full specification is in [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md).

## Status

Phases 1-6 complete: backend foundation, users and workspaces, tasks, notes, the web frontend, and the AI assistant (tool system + chat UI). The assistant currently runs on a built-in **demo model** (`LLM_PROVIDER=fake`); a real AI model is plugged in by adding a provider adapter and an API key. Next: Phase 7 (documents).

## Setup

Requires Docker Desktop and Node.js 20+.

**Backend** (API + Postgres, in Docker):

```
cp .env.example .env          # then edit the values (never commit .env)
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

**Frontend** (Next.js, runs on the host):

```
cd frontend
npm install
npm run dev
```

- App: http://localhost:3000
- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Postgres from the host: `localhost:5433` (5433 avoids clashing with a local Postgres on 5432)

The frontend reads `BACKEND_URL` (server-side only, default `http://localhost:8000`). To change it, create `frontend/.env.local`.

## Common commands

```
docker compose exec backend python -m pytest                    # backend tests
docker compose exec backend alembic revision --autogenerate -m "message"   # new migration
docker compose exec backend alembic upgrade head                # apply migrations
docker compose logs -f backend                                  # follow logs
docker compose down                                             # stop (data kept in volume)

cd frontend && npm run lint && npm run build                    # frontend checks
```

## Architecture

```
Browser -> Next.js (UI + BFF routes) -> FastAPI -> services -> repositories -> PostgreSQL
```

**Backend** (`backend/app/`): `api/` HTTP routes only, `services/` business logic, `repositories/` data access (every query scoped by workspace), `models/` + `schemas/`, `core/` config, logging, errors and security, `db/` session and base.

**Frontend** (`frontend/`): `app/` pages and route handlers, `components/`, `hooks/` (React Query data hooks), `services/` (typed API calls), `lib/` (API client, types, helpers).

**The browser never holds an API token.** Next.js acts as a backend-for-frontend: `/api/session/*` signs in and stores the access and refresh tokens in `httpOnly` cookies, and `/api/backend/*` is an authenticated proxy to the API that attaches the token and refreshes it when it expires. Concurrent refreshes are de-duplicated, because the backend rotates refresh tokens and treats reuse of an old one as theft. Mutating requests must come from the same origin.

### The AI assistant

```
chat endpoint -> AssistantService -> Orchestrator -> LLMProvider (fake today, real model later)
                                          |
                                          +-> ToolRegistry -> TaskService / NoteService (the same code the REST API uses)
```

The model decides *what* to do; only the application's services can do it. Model output is treated as untrusted input: the tool name must be registered and the arguments must pass a strict schema (unknown fields such as `workspace_id` are rejected), failures go back to the model as errors and are never reported as success. The workspace is taken from the authorized request, never from the model. Tools today: `create_task`, `search_tasks`, `create_note`, `search_notes` (no delete or external-send tools yet). Only recent message text is sent to the model as context, not whole histories.

To add a real model, implement `LLMProvider` (`backend/app/llm/types.py`) for it and register it in `backend/app/llm/factory.py`; nothing else changes.

Note: that refresh de-duplication state lives in the Next.js process. A multi-instance deployment needs shared state (for example Redis) or sticky routing.
