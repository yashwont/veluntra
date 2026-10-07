# Veluntra frontend

The web app: Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS and TanStack Query.
See the [project README](../README.md) for what Veluntra is and how to run all of it.

```bash
npm install
npm run dev        # http://localhost:3000 (needs the API on http://localhost:8000)
npm run lint
npx tsc --noEmit
npm run build
```

The API address comes from `BACKEND_URL` (server-side only, default `http://localhost:8000`);
override it in `frontend/.env.local`.

## How it's organised

| Folder | Holds |
|---|---|
| `app/(app)/` | The signed-in pages: Today, Tasks, Notes, Documents, Memory, Search, Connections, Assistant |
| `app/(auth)/` | Login and register |
| `app/api/session/*` | Sign-in, register and sign-out: they set and clear the `httpOnly` token cookies |
| `app/api/backend/[...path]` | Authenticated proxy to the API: attaches the token, refreshes it when it expires, passes uploads and downloads through unchanged |
| `components/` | Shared UI (`ui.tsx`) and feature components |
| `hooks/` | One React Query hook per area (`use-tasks`, `use-documents`, `use-briefing`...) |
| `services/` | Typed API calls, one file per area |
| `lib/` | API client, shared types, date and label helpers |

**The browser never holds an API token.** The server-side routes above are a backend-for-frontend:
tokens stay in cookies JavaScript can't read, and mutating requests must come from the same origin.
Details in [docs/SECURITY.md](../docs/SECURITY.md).

> This project uses a recent Next.js with changes from earlier versions. Before changing framework
> behaviour, read the matching guide in `node_modules/next/dist/docs/`.
