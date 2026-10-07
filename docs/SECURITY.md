# Security

Veluntra holds personal data (tasks, notes, documents, email access), so security decisions
are written down here: what is protected, how, and what is not (yet).

## Controls

| Area | What is in place |
|---|---|
| **Passwords** | Argon2id with a per-password salt, hashed off the event loop. Login takes the same time for unknown emails as for wrong passwords, so response timing doesn't reveal which accounts exist. Minimum length 10. |
| **Sessions** | Short-lived access tokens (15 min) and rotating refresh tokens. Presenting an already-used refresh token revokes all of that user's sessions (it may have been stolen). Tokens are typed, so a refresh token can't act as an access token and an OAuth `state` can't act as either. |
| **Browser** | Tokens live only in `httpOnly`, `SameSite=Lax` cookies (`Secure` in production), never in JavaScript. State-changing requests must come from the same origin. The proxy only forwards to an allow-list of API areas and validates path segments. |
| **Authorization** | Every workspace route requires membership; non-members get a 404, not a 403, so workspace ids can't be probed. Every repository query is filtered by workspace, so a record can't be reached from another workspace even with its id. Personal data inside a workspace (Google connections, suggestions) is additionally filtered by user. |
| **Input** | Pydantic validation on every request. Errors use one format and never include stack traces, SQL or file paths. |
| **Uploads** | Type decided by extension and checked against the file's content; size capped (also while reading); filenames sanitized; files stored under random keys outside any web root, with the key checked against path traversal; downloads are sent as attachments with `nosniff`. Parsers run on untrusted input, so failures become safe messages; PDFs are page-limited and DOCX archives checked against decompression bombs. |
| **AI actions** | Model output is untrusted. A tool must be registered and its arguments must pass a strict schema (unknown fields such as `workspace_id` are rejected). Workspace and user come from the authenticated request, never from the model. Failed tools are reported as failures. There are no delete or send tools, and iterations per message are capped. |
| **Prompt injection** | Stored data, emails, calendar events and files are labelled as information, never instructions, in the system prompt and the tool descriptions. Text from outside the user (event titles) is searched as plain words, never parsed as search commands. Memory text is flattened so it can't forge prompt structure. Emails are truncated before reaching the model. |
| **Google access** | Read-only scopes only. The OAuth `state` is signed, expires in 10 minutes and is bound to a user and workspace. Tokens are encrypted at rest (Fernet) and decrypted only when used. Disconnecting revokes the access at Google. Ids go into Google URLs only after matching a strict pattern. |
| **Approval** | The assistant proposes tasks from email; nothing is created until the user accepts. |
| **Secrets** | `.env` is git-ignored and never committed (checked across the whole history). The generator in `scripts/init_env.py` creates random secrets. CI uses throwaway values. |

## Known limitations

This is a portfolio project, not a hardened production service. Not implemented:

- **No rate limiting** on login or the API. Add it (per IP and per account) before exposing the app publicly.
- **No email verification or password reset.**
- **Single-instance assumptions:** refresh-token de-duplication state lives in the Next.js process; a multi-instance deployment needs shared state or sticky routing.
- **No audit-log UI,** though tool calls are stored with each assistant reply and sensitive actions are logged.
- **Local file storage** only; an object store (S3-compatible) would be needed for multiple servers.
- **Google "restricted" scopes** (Gmail, Drive) require Google's verification review before anyone outside your test users can connect.
- **Demo mode** (`GOOGLE_PROVIDER=demo`, the seeded `demo@veluntra.dev` account) is for local use only; never enable it on a public deployment.

## Reporting a vulnerability

Please use GitHub's private security advisory for this repository rather than filing a public issue.
