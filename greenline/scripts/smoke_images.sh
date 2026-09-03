#!/bin/sh
set -eu

: "${CONTROL_IMAGE:?CONTROL_IMAGE is required}"
: "${WORKER_IMAGE:?WORKER_IMAGE is required}"
: "${POSTGRES_IMAGE:?POSTGRES_IMAGE is required}"
: "${PYTHON_EXECUTION_IMAGE:?PYTHON_EXECUTION_IMAGE is required}"
: "${NODE_EXECUTION_IMAGE:?NODE_EXECUTION_IMAGE is required}"

smoke_parent=${RUNNER_TEMP:-/tmp}
smoke_root="$smoke_parent/greenline-image-smoke-$$"
bundle_root="$smoke_root/run-bundles"
control_name="greenline-control-smoke-$$"
worker_name="greenline-worker-smoke-$$"
postgres_name="greenline-postgres-smoke-$$"
network_name="greenline-smoke-$$"
database_url="postgresql://postgres:postgres@$postgres_name:5432/greenline_ci"

cleanup() {
    docker rm --force "$worker_name" >/dev/null 2>&1 || true
    docker rm --force "$control_name" >/dev/null 2>&1 || true
    docker rm --force "$postgres_name" >/dev/null 2>&1 || true
    docker network rm "$network_name" >/dev/null 2>&1 || true
    rmdir "$bundle_root" >/dev/null 2>&1 || true
    rmdir "$smoke_root" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

mkdir -p "$bundle_root"
chmod 0777 "$bundle_root"

docker network create "$network_name" >/dev/null
docker run --detach \
    --name "$postgres_name" \
    --network "$network_name" \
    --tmpfs /var/lib/postgresql/data:rw,nosuid,nodev,size=256m \
    --env POSTGRES_USER=postgres \
    --env POSTGRES_PASSWORD=postgres \
    --env POSTGRES_DB=greenline_ci \
    "$POSTGRES_IMAGE" >/dev/null

attempt=0
until docker exec "$postgres_name" pg_isready --username postgres --dbname greenline_ci >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        docker logs "$postgres_name"
        exit 1
    fi
    sleep 1
done

for migration in backend/migrations/*.sql
do
    docker exec --interactive "$postgres_name" \
        psql --username postgres --dbname greenline_ci \
        --set ON_ERROR_STOP=1 < "$migration" >/dev/null
done

docker run --detach \
    --name "$control_name" \
    --network "$network_name" \
    --publish 127.0.0.1:18080:18080 \
    --read-only \
    --cap-drop ALL \
    --tmpfs /tmp:rw,nosuid,nodev,size=16m \
    --env GREENLINE_PORT=18080 \
    --env GREENLINE_TRUSTED_PROXY_CIDRS=127.0.0.1/32 \
    --env CLERK_SECRET_KEY=sk_test_image_smoke \
    --env CLERK_AUTHORIZED_PARTIES=http://127.0.0.1:18080 \
    --env GREENLINE_LOG_HMAC_KEY=image-smoke-hmac-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
    --env "GREENLINE_DATABASE_URL=$database_url" \
    "$CONTROL_IMAGE" >/dev/null

attempt=0
until curl --fail --silent http://127.0.0.1:18080/health/ready >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        docker logs "$control_name"
        exit 1
    fi
    sleep 1
done

curl --fail --silent --show-error \
    --header 'Accept: text/html' \
    http://127.0.0.1:18080/ | grep --quiet 'MakeItGreen'
if docker exec "$control_name" sh -c 'command -v docker' >/dev/null 2>&1; then
    echo "control plane unexpectedly contains Docker CLI" >&2
    exit 1
fi

docker run --rm \
    --network none \
    --read-only \
    --cap-drop ALL \
    --user 65534:65534 \
    --tmpfs /tmp:rw,nosuid,nodev,size=16m \
    "$PYTHON_EXECUTION_IMAGE" \
    python -c "import pytest, pytest_jsonreport"
docker run --rm \
    --network none \
    --read-only \
    --cap-drop ALL \
    --user 65534:65534 \
    --tmpfs /tmp:rw,nosuid,nodev,size=16m \
    "$NODE_EXECUTION_IMAGE" \
    node -e "require('node:test')"
if docker run --rm --entrypoint sh "$NODE_EXECUTION_IMAGE" \
    -c 'command -v npm' >/dev/null 2>&1; then
    echo "Node execution image unexpectedly contains npm" >&2
    exit 1
fi

socket_gid=$(docker run --rm \
    --user 0:0 \
    --entrypoint stat \
    --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
    "$WORKER_IMAGE" -c '%g' /var/run/docker.sock)
docker run --detach \
    --name "$worker_name" \
    --network "$network_name" \
    --read-only \
    --cap-drop ALL \
    --group-add "$socket_gid" \
    --tmpfs /tmp:rw,nosuid,nodev,size=16m \
    --mount "type=bind,src=$bundle_root,dst=$bundle_root" \
    --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
    --env "GREENLINE_RUN_BUNDLE_DIR=$bundle_root" \
    --env "GREENLINE_DATABASE_URL=$database_url" \
    --env GREENLINE_LOG_HMAC_KEY=image-smoke-hmac-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
    --env "GREENLINE_PYTHON_EXECUTION_IMAGE=$PYTHON_EXECUTION_IMAGE" \
    --env "GREENLINE_NODE_EXECUTION_IMAGE=$NODE_EXECUTION_IMAGE" \
    "$WORKER_IMAGE" >/dev/null

attempt=0
while :; do
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$worker_name")
    if [ "$health" = healthy ]; then
        break
    fi
    attempt=$((attempt + 1))
    if [ "$health" = unhealthy ] || [ "$attempt" -ge 45 ]; then
        docker logs "$worker_name"
        docker inspect "$worker_name"
        exit 1
    fi
    sleep 1
done

docker exec "$worker_name" python -c \
    "import importlib.util; assert importlib.util.find_spec('fastapi') is None; assert importlib.util.find_spec('clerk_backend_api') is None"

docker stop --time 75 "$worker_name" >/dev/null
docker stop --time 10 "$control_name" >/dev/null
