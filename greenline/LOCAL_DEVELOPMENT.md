# Running MakeItGreen locally

This guide explains how to install, start, test, stop, and troubleshoot
MakeItGreen on your own computer before a change reaches staging or production.

## What local mode runs

Local mode starts two processes:

1. A FastAPI backend at `http://127.0.0.1:8000`.
2. A Vite/React frontend at `http://127.0.0.1:5173`.

Vite proxies browser requests under `/api` to the backend. Challenge tests run
as local subprocesses using the backend Python environment or the installed
Node runtime. Learner edits, progress, run history, logs, and PID files stay
under ignored local directories in `greenline/backend/data/`.

Local mode does **not** require PostgreSQL, Caddy, the hosted execution worker,
the production Compose files, or production container images. Those belong to
the hosted deployment path.

## Prerequisites

Install these tools before the first run:

- Git.
- Python 3.12 or 3.13.
- Node.js 22 and npm.
- `curl` and `lsof` (already included with macOS).
- Docker Desktop only if you want to build or smoke-test production images.

Check the main versions:

```bash
python3 --version
node --version
npm --version
```

All commands below assume the checkout has this layout:

```text
InvPrep/
├── green                 local process launcher
└── greenline/            application source
```

## First-time installation

Start in the directory that contains both `green` and `greenline`:

```bash
cd /path/to/InvPrep
```

Create the backend virtual environment and install the pinned development
dependencies:

```bash
cd greenline/backend
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
cd ../..
```

Install the exact frontend dependency graph from `package-lock.json`:

```bash
cd greenline/frontend
npm ci
cd ../..
```

### Simplest configuration: local mode without sign-in

Create `greenline/backend/.env.local` with only this content:

```dotenv
GREENLINE_MODE=local
```

Do not define `CLERK_SECRET_KEY` in that file, and do not define
`VITE_CLERK_PUBLISHABLE_KEY` in `greenline/frontend/.env`. When both are absent,
the local frontend and API intentionally run without authentication.

Both files are ignored by Git. Never commit real keys or paste production
secrets into a local-development document.

### Optional configuration: test Clerk authentication locally

Use keys from the same Clerk development instance:

```dotenv
# greenline/backend/.env.local
GREENLINE_MODE=local
CLERK_SECRET_KEY=sk_test_replace_with_your_development_key
CLERK_AUTHORIZED_PARTIES=http://localhost:5173,http://127.0.0.1:5173
```

```dotenv
# greenline/frontend/.env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_replace_with_your_development_key
```

The backend secret and frontend publishable key must belong to the same Clerk
development instance. Restart both processes after changing either environment
file.

## Start the application

From `InvPrep/`, run:

```bash
./green start
```

Wait for both readiness messages:

```text
Backend ready: http://127.0.0.1:8000/health/live
Frontend ready: http://127.0.0.1:5173/
```

Then open:

```text
http://127.0.0.1:5173
```

Keep that terminal open. `./green start` owns the two development processes and
stops them when you press `Ctrl+C`.

Useful launcher commands:

```bash
./green status
./green logs
./green restart
./green stop
```

The launcher writes logs to:

```text
greenline/backend/data/dev-server/backend.log
greenline/backend/data/dev-server/frontend.log
```

## Verify that the stack works

Check the backend:

```bash
curl -i http://127.0.0.1:8000/health/live
```

The expected response is HTTP 200 with local mode:

```json
{"status":"live","mode":"local"}
```

Check the frontend:

```bash
curl -I http://127.0.0.1:5173/
```

In the browser, open a challenge, edit an allowed source file, and select
**Run tests**. A valid starter repository should show intentional test failures;
that is the learner's starting point, not an infrastructure failure.

## Run the automated checks

### Validate every challenge

This is the most important content check. It runs every starter and every
reference solution, including language variants:

```bash
cd greenline
backend/venv/bin/python scripts/validate_challenges.py
```

A successful run ends with:

```text
55/55 challenge variants valid (pristine fails, solution passes).
```

The validator also enforces these catalog rules:

- Every solved implementation has at least 15 test cases.
- Every untouched starter retains 1–5 passing cases and still fails overall.
- Reference solutions cannot replace protected tests or pytest configuration.
- Python and Node imports must be available in their production execution
  environments.

### Run all backend tests

From `greenline/`:

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests -q
```

### Run frontend tests, lint, and build

```bash
cd greenline/frontend
npm test
npm run lint
npm run build
```

### Run one Python starter directly

This is useful while authoring a specific challenge. The starter is expected to
exit with test failures:

```bash
cd greenline/challenges/orders-service/repo
../../../backend/venv/bin/python -m pytest -q --color=no -p no:cacheprovider
```

Use the catalog validator to test the protected reference-solution overlay;
do not copy solution files into the committed starter repository.

### Run one JavaScript starter directly

```bash
cd greenline/challenges/config-merge/variants/javascript/repo
node --test
```

## The normal local change workflow

Use this sequence before considering a deployment:

1. Pull or switch to the intended branch.
2. Run `./green start` from `InvPrep/`.
3. Reproduce the behavior in the browser.
4. Make the code or challenge-content change.
5. Re-test the affected behavior in the browser.
6. Run the relevant focused test file.
7. Run the whole challenge validator when challenge content changed.
8. Run the full backend or frontend suite for the area changed.
9. Run `git diff --check` and inspect `git diff`.
10. Commit and push only after the local checks are green.
11. Let CI build and test the production-shaped images.
12. Promote the same immutable image digests through staging before production.

Local mode proves application behavior quickly. CI and staging prove the
production container, networking, PostgreSQL, TLS, Clerk, and worker topology.
You need both layers; local testing alone is not a production deployment test.

## Local mode versus hosted mode

| Concern | Local development | Hosted deployment |
|---|---|---|
| Frontend | Vite development server | Built into control-plane image |
| API | Uvicorn with reload | Control-plane container |
| Learner state | Local files and SQLite | PostgreSQL |
| Test execution | Trusted host subprocess | Isolated Docker execution image |
| Queue | In-process/local adapter | PostgreSQL run jobs and worker |
| Reverse proxy/TLS | Not required | Caddy and public HTTPS |
| Authentication | Optional | Required Clerk production configuration |
| Purpose | Fast development feedback | Production behavior and security |

Do not start the production Compose files just to make ordinary code changes.
Use them only when testing the hosted deployment contract.

## Troubleshooting

### `Missing required file: .../backend/.env.local`

Create `greenline/backend/.env.local` and set `GREENLINE_MODE=local`.

### `Missing required file: .../backend/venv/bin/uvicorn`

Create the backend virtual environment and install `backend/requirements.txt`.

### `Missing required file: .../frontend/node_modules/.bin/vite`

Run `npm ci` inside `greenline/frontend`.

### Port 8000 or 5173 is already in use

Check the managed processes and logs:

```bash
./green status
./green stop
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

You can choose alternate ports for the launcher:

```bash
GREEN_BACKEND_PORT=8010 GREEN_FRONTEND_PORT=5180 ./green start
```

The current Vite proxy is fixed to backend port 8000, so changing only the
launcher backend port also requires updating `frontend/vite.config.ts`. For the
normal workflow, free ports 8000 and 5173 instead.

### Browser shows `Backend unreachable`

Run `./green status`, inspect `./green logs`, and verify
`http://127.0.0.1:8000/health/live` directly.

### API responds with `authentication required`

The backend has a Clerk secret configured. Either configure the matching
frontend Clerk publishable key and sign in, or remove both Clerk variables for
the auth-free local workflow and restart the stack.

### A challenge reports `No module named ...`

Do not fix this by installing a package globally. Determine which execution
contract owns it:

- Platform-wide packages belong in
  `backend/execution-images/python/requirements.txt` and require a rebuilt image.
- A deliberately isolated Python challenge must declare its read-only
  requirements file in `challenge.json`.
- Node challenges may use relative modules and built-in `node:` modules; the
  hardened execution image does not install npm packages during a run.

Then run the full challenge validator again. It rejects imports that would work
only because of an accidental package in a developer environment.

### Reset local learner state

Use the product's **Reset** action to reset one challenge. If you intentionally
need a completely clean local profile, stop the stack first and move the
ignored `greenline/backend/data/` directory somewhere safe before restarting.
That directory contains local workspaces, progress, history, logs, and process
state, so do not delete it casually.

## Before pushing or deploying

At minimum, run:

```bash
cd greenline
backend/venv/bin/python scripts/validate_challenges.py
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run lint
npm run build
```

After those checks pass, review the diff, commit the intended files, push the
branch, and use CI plus staging as the production rehearsal. Do not diagnose a
new change for the first time on the production servers.
