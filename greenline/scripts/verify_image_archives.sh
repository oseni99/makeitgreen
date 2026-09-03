#!/bin/sh
set -eu

: "${ARCHIVE_DIR:?ARCHIVE_DIR is required}"
: "${CONTROL_IMAGE:=greenline-control-plane:ci}"
: "${WORKER_IMAGE:=greenline-execution-worker:ci}"
: "${PYTHON_EXECUTION_IMAGE:=greenline-python-execution:ci}"
: "${NODE_EXECUTION_IMAGE:=greenline-node-execution:ci}"

active_container=
cleanup() {
    if [ -n "$active_container" ]; then
        docker rm --force "$active_container" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

case "$ARCHIVE_DIR" in
    /*) ;;
    *)
        echo "ARCHIVE_DIR must be absolute" >&2
        exit 1
        ;;
esac

verify_archive() {
    component=$1
    image=$2
    archive="$ARCHIVE_DIR/$component.oci.tar"
    if [ ! -f "$archive" ]; then
        echo "missing OCI archive: $archive" >&2
        exit 1
    fi
    active_container=$(docker create "$image")
    runtime_digest=$(docker inspect \
        --format '{{.ImageManifestDescriptor.digest}}' "$active_container")
    docker rm "$active_container" >/dev/null
    active_container=
    index_digest=$(tar -xOf "$archive" index.json | jq -r '.manifests[0].digest')
    index_hex=${index_digest#sha256:}
    archive_digest=$(tar -xOf "$archive" "blobs/sha256/$index_hex" | jq -r '
        [.manifests[] |
          select(.annotations["vnd.docker.reference.type"] != "attestation-manifest") |
          .digest] |
        if length == 1 then .[0] else error("expected one runnable manifest") end
    ')

    if [ "$runtime_digest" != "$archive_digest" ]; then
        echo "$component archive does not contain the scanned runtime manifest" >&2
        exit 1
    fi
}

verify_archive control-plane "$CONTROL_IMAGE"
verify_archive execution-worker "$WORKER_IMAGE"
verify_archive python-execution "$PYTHON_EXECUTION_IMAGE"
verify_archive node-execution "$NODE_EXECUTION_IMAGE"
