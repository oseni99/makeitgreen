# Clerk authentication

MakeItGreen uses Clerk for identity and Google as its only sign-in method.

## Clerk Dashboard

1. Create or select the Clerk application.
2. Enable the Google social connection.
3. Disable email/password, magic-link, phone, and other social connections.
4. Set production access mode to **Open** so a new learner can create an
   account without an invitation.
5. Add `http://localhost:5173` as a development origin and redirect URL.

The application does not use an enrollment claim. A valid Clerk session is the
authorization boundary for learner routes; `beta_access` metadata and session
claims are neither required nor trusted by the backend.

The UI intentionally exposes one entry point: **Sign in with Google**. The
provider allowlist is enforced by the Clerk application configuration rather
than by trusting a client-side label.

## Local environment

Copy the example files and fill in the keys:

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env.local
```

Set `GREENLINE_MODE=local` for the current trusted personal workflow. Runtime mode
is mandatory: a missing or unknown value stops application composition. Hosted Mode
requires Clerk identity, isolated execution, durable state and coordination, abuse
controls, trusted proxy configuration, and structured security logging.

Vite loads the frontend key automatically. The backend does not load dotenv
files itself, so export the values before starting Uvicorn (or load them with
your normal environment manager). The README command sources `.env.local`:

```bash
export CLERK_SECRET_KEY=sk_test_...
export CLERK_AUTHORIZED_PARTIES=http://localhost:5173,http://127.0.0.1:5173
```

The hosted frontend key is compiled into the control-plane image. Configure the
GitHub repository variable `VITE_CLERK_PUBLISHABLE_KEY` before releasing;
default-branch image builds refuse to publish without a `pk_test_` or `pk_live_`
value. This key is intentionally public. Keep `CLERK_SECRET_KEY` exclusively in
the deployment platform's runtime secret store.

## Hosted secret and proxy configuration

Hosted deployments should mount secrets as files and set
`CLERK_SECRET_KEY_FILE`, `CLERK_JWT_KEY_FILE`, `GREENLINE_DATABASE_URL_FILE`, and
`GREENLINE_LOG_HMAC_KEY_FILE`. Direct values remain supported for secret managers
that inject environment variables, but a direct and `_FILE` form may never be
set together. File paths must be absolute; unreadable, empty, oversized, or
ambiguous secret sources fail composition without exposing their contents.

`CLERK_JWT_KEY_FILE` contains the Clerk application's PEM JWT public key from
**Clerk Dashboard → API keys → Show JWT public key → PEM Public Key**. Hosted
Mode requires it and verifies session tokens locally, avoiding a remote JWKS
request on the protected API path. Rotate it together with the Clerk instance's
signing keys.

Set `GREENLINE_TRUSTED_PROXY_CIDRS` to the explicit IP networks of the load
balancer or ingress. Wildcard trust is rejected. Start Hosted Mode through
`backend/serve.py`, which configures Uvicorn's proxy-header allowlist and disables
the identifying Server header. Network policy must also prevent public clients
from connecting directly to the application port.

Security events are emitted as one-line JSON. Clerk subjects are represented by
a stable HMAC pseudonym derived from `GREENLINE_LOG_HMAC_KEY`; tokens, raw
subjects, request bodies, learner file paths, and database URLs are never logged.

When `CLERK_SECRET_KEY` is present, every `/api/*` request must carry a valid
Clerk session bearer token. Without it, the app stays in local compatibility
mode so the existing offline development and test workflow remains usable.

Authenticated workspace files, progress, run history, and background run-job
polling are keyed by Clerk's verified `sub` claim. The local SQLite/workspace
paths use a SHA-256 namespace derived from that subject, so the subject itself
is never used as a filesystem path. Requests without configured Clerk keys keep
the legacy single-user local paths for offline development and tests.

Hosted challenge metadata is split by exposure level. The catalog returns only
the summary needed to browse; full briefs, repository files, search results,
and solutions are tracked as Challenge Content reads. Bulk access across many
challenges or solutions is temporarily blocked and emitted as a structured
security event. Solution content is returned only after that learner has solved
or explicitly spoiled the challenge.
