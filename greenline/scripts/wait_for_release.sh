#!/bin/sh
set -eu

: "${RELEASE_HEALTH_URL:?RELEASE_HEALTH_URL is required}"
: "${EXPECTED_SOURCE_SHA:?EXPECTED_SOURCE_SHA is required}"
: "${EXPECTED_PYTHON_EXECUTION_DIGEST:?EXPECTED_PYTHON_EXECUTION_DIGEST is required}"
: "${EXPECTED_NODE_EXECUTION_DIGEST:?EXPECTED_NODE_EXECUTION_DIGEST is required}"

case "$RELEASE_HEALTH_URL" in
    https://*|http://127.0.0.1:*|http://localhost:*) ;;
    *)
        echo "RELEASE_HEALTH_URL must use HTTPS (HTTP is allowed only for localhost tests)" >&2
        exit 1
        ;;
esac
if [ "${#EXPECTED_SOURCE_SHA}" -ne 40 ] || \
    printf '%s' "$EXPECTED_SOURCE_SHA" | grep -q '[^0-9a-f]'; then
    echo "EXPECTED_SOURCE_SHA must be a full lowercase commit SHA" >&2
    exit 1
fi
for digest in "$EXPECTED_PYTHON_EXECUTION_DIGEST" "$EXPECTED_NODE_EXECUTION_DIGEST"
do
    hex=${digest#sha256:}
    if [ "$hex" = "$digest" ] || [ "${#hex}" -ne 64 ] || \
        printf '%s' "$hex" | grep -q '[^0-9a-f]'; then
        echo "expected execution image digests must be lowercase sha256 digests" >&2
        exit 1
    fi
done

attempts=${ROLLOUT_ATTEMPTS:-30}
interval=${ROLLOUT_INTERVAL_SECONDS:-10}
case "$attempts" in
    ''|*[!0-9]*|0)
        echo "ROLLOUT_ATTEMPTS must be a positive integer" >&2
        exit 1
        ;;
esac
case "$interval" in
    ''|*[!0-9]*)
        echo "ROLLOUT_INTERVAL_SECONDS must be a non-negative integer" >&2
        exit 1
        ;;
esac

response=$(mktemp)
trap 'rm -f "$response"' EXIT HUP INT TERM
attempt=1
while [ "$attempt" -le "$attempts" ]; do
    if curl --silent --show-error --fail \
        --connect-timeout 5 --max-time 10 --retry 2 --retry-all-errors \
        --output "$response" "$RELEASE_HEALTH_URL" && \
        jq -e --arg expected "$EXPECTED_SOURCE_SHA" \
            --arg python_digest "$EXPECTED_PYTHON_EXECUTION_DIGEST" \
            --arg node_digest "$EXPECTED_NODE_EXECUTION_DIGEST" \
            '.status == "ready" and .source_sha == $expected and
             .worker.status == "ready" and .worker.source_sha == $expected and
             (.worker.python_execution_image | type == "string" and
                endswith("@" + $python_digest)) and
             (.worker.node_execution_image | type == "string" and
                endswith("@" + $node_digest))' \
            "$response" >/dev/null; then
        echo "release $EXPECTED_SOURCE_SHA is ready"
        exit 0
    fi
    if [ "$attempt" -lt "$attempts" ]; then
        sleep "$interval"
    fi
    attempt=$((attempt + 1))
done

echo "release $EXPECTED_SOURCE_SHA did not become ready at $RELEASE_HEALTH_URL" >&2
exit 1
