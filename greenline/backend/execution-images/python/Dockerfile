# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}
ARG PYTHON_BASE_IMAGE
ARG SOURCE_URL
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source=${SOURCE_URL} \
    org.opencontainers.image.revision=${SOURCE_REVISION}
RUN digest="${PYTHON_BASE_IMAGE##*@sha256:}"; \
    [ "$digest" != "$PYTHON_BASE_IMAGE" ] && [ "${#digest}" -eq 64 ] && \
    ! printf '%s' "$digest" | grep -q '[^0-9a-f]'

COPY requirements.txt /opt/greenline/requirements.txt
RUN python -m pip install --no-cache-dir \
    --requirement /opt/greenline/requirements.txt && \
    python -m pip uninstall --yes pip

# The Adapter supplies the command, numeric user, read-only root filesystem,
# and all resource/isolation controls at container creation time.
WORKDIR /workspace
