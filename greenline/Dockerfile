# syntax=docker/dockerfile:1.7

# Supply approved index digests, for example node:22-bookworm-slim@sha256:...
# Builds intentionally fail when either immutable base reference is omitted.
ARG NODE_BASE
ARG PYTHON_BASE

FROM ${NODE_BASE} AS frontend-build
ARG NODE_BASE
RUN digest="${NODE_BASE##*@sha256:}"; \
    [ "$digest" != "$NODE_BASE" ] && [ "${#digest}" -eq 64 ] && \
    ! printf '%s' "$digest" | grep -q '[^0-9a-f]'
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
RUN npm run build

FROM ${PYTHON_BASE} AS python-dependencies
ARG PYTHON_BASE
RUN digest="${PYTHON_BASE##*@sha256:}"; \
    [ "$digest" != "$PYTHON_BASE" ] && [ "${#digest}" -eq 64 ] && \
    ! printf '%s' "$digest" | grep -q '[^0-9a-f]'
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/greenline-venv
COPY backend/requirements-production.txt /tmp/requirements-production.txt
RUN /opt/greenline-venv/bin/pip install --requirement /tmp/requirements-production.txt

FROM ${PYTHON_BASE} AS control-plane
ARG SOURCE_URL
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source=${SOURCE_URL} \
    org.opencontainers.image.revision=${SOURCE_REVISION}
ENV PATH=/opt/greenline-venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GREENLINE_MODE=hosted \
    GREENLINE_FRONTEND_DIST=/app/frontend \
    GREENLINE_RELEASE_SHA=${SOURCE_REVISION} \
    GREENLINE_HOST=0.0.0.0 \
    GREENLINE_PORT=8000
WORKDIR /app/backend
COPY --from=python-dependencies /opt/greenline-venv /opt/greenline-venv
RUN /usr/local/bin/python -m pip uninstall --yes pip && \
    /opt/greenline-venv/bin/python -m pip uninstall --yes pip
COPY backend/*.py ./
COPY backend/migrations ./migrations
COPY challenges /app/challenges
COPY --from=frontend-build /build/frontend/dist /app/frontend
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]
CMD ["python", "serve.py"]
