# syntax=docker/dockerfile:1.7

ARG NODE_BASE_IMAGE
FROM ${NODE_BASE_IMAGE}
ARG NODE_BASE_IMAGE
ARG SOURCE_URL
ARG SOURCE_REVISION
RUN apt-get update && \
    apt-get install --only-upgrade --yes libpcre2-8-0 && \
    rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.source=${SOURCE_URL} \
    org.opencontainers.image.revision=${SOURCE_REVISION}
RUN digest="${NODE_BASE_IMAGE##*@sha256:}"; \
    [ "$digest" != "$NODE_BASE_IMAGE" ] && [ "${#digest}" -eq 64 ] && \
    ! printf '%s' "$digest" | grep -q '[^0-9a-f]'

# Challenges use node:test and never install packages during a run.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-* && \
    rm -f /usr/local/bin/npm /usr/local/bin/npx \
        /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg /usr/local/bin/pnpm /usr/local/bin/pnpx

WORKDIR /workspace
