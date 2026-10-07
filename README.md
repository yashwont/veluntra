# Veluntra

[![CI](https://github.com/yashwont/veluntra/actions/workflows/ci.yml/badge.svg)](https://github.com/yashwont/veluntra/actions/workflows/ci.yml)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)

**An AI-powered personal operations system.** Tasks, notes, documents, long-term memory and your Google
calendar, mail and Drive in one private place, with an assistant that can act on all of it, but only
through validated backend services, never by touching the database itself.

It started as a question: *how do you let an AI act on someone's personal data and still trust it?*
The answer here: the model proposes, the application's own rules decide, the user approves anything that
matters, and every action is recorded.

<!-- Screenshots: add images to docs/screenshots/ and uncomment.
![Today](docs/screenshots/today.png)
![Assistant](docs/screenshots/assistant.png)
-->

## Try it (about 5 minutes, no accounts, no API keys, no cost)

You need **Docker Desktop**, **Python 3** and **Node.js 20+**.

```bash
git clone https://github.com/yashwont/veluntra.git
cd veluntra

python scripts/init_env.py                  # creates .env with random secrets, demo mode on
docker compose up -d --build                # database + API (applies migrations on start)
docker compose exec backend python -m scripts.seed_demo   # sample tasks, notes, documents, memories

cd frontend && npm install && npm run dev   # the web app
```

Open **http://localhost:3000** and sign in with **`demo@veluntra.dev`** / **`demo-password-123`**.
(Run the seed command once the API is up, about ten seconds after `docker compose up`. On Windows, use
`py` if `python` isn't found.)

**What to try**

| Open | What you'll see |
|---|---|
| **Today** | "Prepare me for today": ranked priorities with reasons, overdue tasks, follow-ups |
| **Connections** → *Connect Google* | Instant sample Google account. Then **Today** also shows meetings (with a scheduling clash and your related notes and documents), and **Scan my email** proposes tasks you can accept or dismiss |
| **Assistant** | Try: *"Remember that Priya likes Friday meetings"*, *"Create a high priority task to call Ram tomorrow"*, *"What is on my calendar today?"*, *"Search everything for pricing"*, *"Prepare me for today"* |
| **Search** | One box over everything. Try `pricing`, `is:overdue`, `kind:person`, `type:documents revenue` |
| **Documents** | Upload a PDF, DOCX, TXT or MD file; it is processed in the background and becomes searchable |
| **Memory** | What the assistant remembered, with where it came from. Edit or forget anything |

### About the "demo" parts (read this)

To make the project free and runnable by anyone, three things are **built-in stand-ins**, each behind an
interface so the real thing is a small adapter away:

| Stand-in | What it is | Real version |
|---|---|---|
| **Assistant model** (`LLM_PROVIDER=fake`) | A rule-based parser that understands a few phrasings and emits real tool calls. *Not* intelligent: it exists to exercise the real pipeline (validation, tools, storage, UI). | Implement `LLMProvider` (`backend/app/llm/types.py`) |
| **Embeddings** (`EMBEDDING_PROVIDER=fake`) | Hashes words into vectors: matches shared words, not meaning. | Implement `EmbeddingProvider` (`backend/app/embeddings/types.py`) |
| **Google** (`GOOGLE_PROVIDER=demo`) | Canned, clearly fake calendar, mail and Drive data. | Add your own OAuth client: [docs/GOOGLE_SETUP.md](docs/GOOGLE_SETUP.md) |

Everything else (authentication, workspaces, tasks, notes, document pipeline, search, memory, OAuth,
encryption, briefing, suggestions) is the real implementation.

## What's inside

- **Accounts and workspaces:** Argon2 passwords, rotating refresh tokens with reuse detection, and per-workspace isolation enforced in every query.
- **Tasks and notes:** priorities, due dates, tags, full-text search.
- **Documents:** upload TXT/MD/PDF/DOCX → validated and stored → text extracted, chunked and embedded in the background → semantic search.
- **Memory:** durable facts with provenance, saved only when worth remembering, with duplicate and size limits.
- **Unified search:** tasks and notes by full-text SQL, documents and memories by meaning, merged into one ranked list, with filters typed into the query.
- **Assistant:** a tool system where the model's output is untrusted, validated against strict schemas, and can only call the same services the REST API uses.
- **Google (read-only):** Gmail, Calendar with conflict detection, and Drive (importable into Documents); OAuth with signed state, encrypted tokens and revocation.
- **Proactive:** a daily briefing and email-derived suggestions that need your approval before becoming tasks.

## How it's built

```
Browser → Next.js (UI + backend-for-frontend) → FastAPI → services → repositories → PostgreSQL + pgvector
```

**Stack:** Python 3.12 · FastAPI · async SQLAlchemy 2 · Alembic · PostgreSQL 16 with pgvector · Next.js 16 · React 19 · TypeScript · Tailwind · TanStack Query · Docker Compose · GitHub Actions.

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, data model, the assistant flow, search, and the decisions behind them
- [docs/SECURITY.md](docs/SECURITY.md): what is protected and how, and the honest list of what isn't
- [docs/GOOGLE_SETUP.md](docs/GOOGLE_SETUP.md): connecting a real Google account
- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md): the original product brief this was built from

## Tests and quality

Over **350 backend tests** run on every push (real Postgres with pgvector, real migrations), alongside
frontend lint, type-check and production build. CI also fails if the database models and migrations
drift apart.

```bash
docker compose exec backend python -m pytest      # backend tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

## Everyday commands

```bash
docker compose exec backend alembic revision --autogenerate -m "message"   # new migration
docker compose exec backend python -m scripts.seed_demo --reset            # recreate the demo account
docker compose logs -f backend                                             # follow logs
docker compose down                                                        # stop (data is kept)
```

Services: app `localhost:3000` · API `localhost:8000` (Swagger at `/docs`) · Postgres `localhost:5433`.

## Roadmap

Ideas for taking it further: a real LLM and embedding adapter (a local model through Ollama would keep it
free), a job queue for background work, rate limiting, email verification, object storage for documents,
and a proactive scheduler for the email scan.

## License

[MIT](LICENSE)
