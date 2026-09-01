# MakeItGreen

MakeItGreen is a repository-based backend interview practice platform. It
provides realistic broken codebases, deterministic tests, a browser workspace,
sandboxed challenge execution, learner progress tracking, and reviewed
reference solutions.

The application lives in [`greenline/`](greenline/). Its detailed
[README](greenline/README.md) covers the architecture, local setup, hosted
deployment, release gates, and challenge-authoring workflow.

## Run locally

Prerequisites and environment variables are documented in
[`greenline/README.md`](greenline/README.md). After configuring them, start the
frontend and backend together from the repository root:

```bash
./green start
```

The frontend is served at <http://127.0.0.1:5173> and the API at
<http://127.0.0.1:8000>. Manage the development stack with:

```bash
./green status
./green logs
./green restart
./green stop
```

## Documentation

- [Architecture](greenline/ARCHITECTURE.md)
- [Authentication](greenline/AUTH.md)
- [Beta deployment](greenline/DEPLOY_DIGITALOCEAN.md)
- [Release operations](greenline/RELEASES.md)
- [Design system](greenline/DESIGN.md)

## Project structure

```text
greenline/
├── backend/      FastAPI API, learner state, and execution coordination
├── frontend/     React, TypeScript, Vite, Tailwind, and Monaco workspace
├── challenges/   Broken repositories, tests, metadata, and solutions
└── scripts/      Validation, release, migration, and smoke-test tooling
```
