# Challenge Run images

The container execution Adapter never pulls or builds images while handling a
Challenge Run. Build, scan, publish, and preload the images during deployment,
then configure their immutable registry digests.

The Python image contains the platform's supported pytest toolchain plus the
FastAPI/Pydantic/HTTPX contract used by API challenges. Challenge validation
rejects undeclared third-party imports before catalog content can ship:

```bash
docker build -t registry.example.com/greenline-python:2026-09 \
  --build-arg PYTHON_BASE_IMAGE='python:3.13-slim@sha256:<approved-index-digest>' \
  backend/execution-images/python
docker push registry.example.com/greenline-python:2026-09
```

The Node challenges use only the built-in `node:test` runner. Build the dedicated
image, which removes package managers and their unnecessary dependency surface:

```bash
docker build -t registry.example.com/greenline-node:2026-09 \
  --build-arg NODE_BASE_IMAGE='node:22-bookworm-slim@sha256:<approved-index-digest>' \
  backend/execution-images/node
docker push registry.example.com/greenline-node:2026-09
```

Record both published references in `name@sha256:<64 hex characters>` form as
`GREENLINE_PYTHON_EXECUTION_IMAGE` and `GREENLINE_NODE_EXECUTION_IMAGE`.

Execution Worker startup runs `docker version`, inspects both exact digest
references, and asks the daemon to bind a disposable probe created under
`GREENLINE_RUN_BUNDLE_DIR`. It fails unless the daemon can see that shared path.
The worker image healthcheck repeats these checks together with PostgreSQL
readiness. Readiness never pulls or builds an image.

The images must provide `/bin/sh` and `cp`. They do not need an entrypoint: the
Adapter supplies a fixed bootstrap that copies the read-only Run Bundle into a
size-bounded tmpfs workspace before executing the trusted challenge command.
