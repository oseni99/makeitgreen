#!/bin/sh
set -eu

: "${ARCHIVE_DIR:?ARCHIVE_DIR is required}"
: "${CONTROL_IMAGE:=greenline-control-plane:ci}"
: "${WORKER_IMAGE:=greenline-execution-worker:ci}"
: "${PYTHON_EXECUTION_IMAGE:=greenline-python-execution:ci}"
: "${NODE_EXECUTION_IMAGE:=greenline-node-execution:ci}"

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
    case "$image" in
        *@sha256:*) runtime_digest=${image##*@} ;;
        *)
            echo "$component scanned image is not digest-pinned" >&2
            exit 1
            ;;
    esac
    runtime_hex=${runtime_digest#sha256:}
    if [ "${#runtime_hex}" -ne 64 ] || \
        printf '%s' "$runtime_hex" | grep -q '[^0-9a-f]'; then
        echo "$component scanned image has an invalid digest" >&2
        exit 1
    fi
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
