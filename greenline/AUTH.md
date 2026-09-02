# Clerk authentication

MakeItGreen uses Clerk for identity and Google as its only sign-in method.

## Clerk Dashboard

1. Create or select the Clerk application.
2. Enable the Google social connection.
3. Disable email/password, magic-link, phone, and other social connections.
4. Add `http://localhost:5173` as a development origin and redirect URL.

The UI intentionally exposes one entry point: **Sign in with Google**. The
provider allowlist is enforced by the Clerk application configuration rather
than by trusting a client-side label.

## Local environment

Copy the example files and fill in the keys:

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

Vite loads the frontend key automatically. Export the backend values before
starting Uvicorn (or load them with your normal environment manager):

```bash
export CLERK_SECRET_KEY=sk_test_...
export CLERK_AUTHORIZED_PARTIES=http://localhost:5173,http://127.0.0.1:5173
```

When `CLERK_SECRET_KEY` is present, every `/api/*` request must carry a valid
Clerk session bearer token. Without it, the app stays in local compatibility
mode so the existing offline development and test workflow remains usable.

Authenticated workspace files, progress, run history, and background run-job
polling are keyed by Clerk's verified `sub` claim. The local SQLite/workspace
paths use a SHA-256 namespace derived from that subject, so the subject itself
is never used as a filesystem path. Requests without configured Clerk keys keep
the legacy single-user local paths for offline development and tests.
