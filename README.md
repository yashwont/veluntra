# Veluntra

An AI-powered personal operations system: tasks, notes, documents and conversations in one private command center, with an AI layer that acts only through validated backend services.

The full specification is in [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md).

## Status

Phase 1 (backend foundation) complete. Next: Phase 2 (users and workspaces).

## Setup

Requires Docker Desktop.

```
cp .env.example .env          # then edit the values (never commit .env)
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Postgres from the host: `localhost:5433` (5433 avoids clashing with a local Postgres on 5432)

## Common commands

```
docker compose exec backend python -m pytest                    # run tests
docker compose exec backend alembic revision --autogenerate -m "message"   # new migration
docker compose exec backend alembic upgrade head                # apply migrations
docker compose logs -f backend                                  # follow logs
docker compose down                                             # stop (data kept in volume)
```

## Backend layout

```
backend/app/
  api/      HTTP routes only (validation, auth, status codes)
  core/     config, logging, errors, security
  db/       SQLAlchemy base and session
  main.py   app factory
```

Business logic goes in `services/` (added in Phase 2); routes never contain it.
