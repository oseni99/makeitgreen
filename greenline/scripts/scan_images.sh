#!/bin/sh
set -eu

: "${TRIVY_IMAGE:?TRIVY_IMAGE is required}"
: "${CONTROL_IMAGE:?CONTROL_IMAGE is required}"
: "${WORKER_IMAGE:?WORKER_IMAGE is required}"
: "${PYTHON_EXECUTION_IMAGE:?PYTHON_EXECUTION_IMAGE is required}"
: "${NODE_EXECUTION_IMAGE:?NODE_EXECUTION_IMAGE is required}"

scan_parent=${RUNNER_TEMP:-/tmp}
scan_root="$scan_parent/greenline-image-scan-$$"
active_container=
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ignore_file="$script_dir/../.trivyignore.yaml"

cleanup() {
    if [ -n "$active_container" ]; then
        docker rm --force "$active_container" >/dev/null 2>&1 || true
    fi
    case "$scan_root" in
        "$scan_parent"/greenline-image-scan-*) rm -rf -- "$scan_root" ;;
    esac
}
trap cleanup EXIT INT TERM

mkdir -p "$scan_root"

if [ -n "${SBOM_DIR:-}" ]; then
    case "$SBOM_DIR" in
        /*) ;;
        *)
            echo "SBOM_DIR must be an absolute path" >&2
            exit 1
            ;;
    esac
    mkdir -p "$SBOM_DIR"
fi

scan_image() {
    image_name=$1
    image_ref=$2
    rootfs="$scan_root/$image_name"
    archive="$scan_root/$image_name.tar"
    mkdir -p "$rootfs"

    active_container=$(docker create "$image_ref")
    docker export --output "$archive" "$active_container"
    docker rm "$active_container" >/dev/null
    active_container=
    tar -xf "$archive" -C "$rootfs"
    rm -f -- "$archive"

    docker run --rm \
        --mount "type=bind,src=$rootfs,dst=/target,readonly" \
        --mount "type=bind,src=$ignore_file,dst=/policy/.trivyignore.yaml,readonly" \
        --mount type=volume,src=greenline-trivy-cache,dst=/root/.cache \
        "$TRIVY_IMAGE" rootfs --scanners vuln --ignore-unfixed \
        --ignorefile /policy/.trivyignore.yaml \
        --severity HIGH,CRITICAL --exit-code 1 /target

    if [ -n "${SBOM_DIR:-}" ]; then
        docker run --rm \
            --mount "type=bind,src=$rootfs,dst=/target,readonly" \
            --mount "type=bind,src=$SBOM_DIR,dst=/artifacts" \
            --mount type=volume,src=greenline-trivy-cache,dst=/root/.cache \
            "$TRIVY_IMAGE" rootfs --format spdx-json \
            --output "/artifacts/$image_name.spdx.json" /target
    fi

    rm -rf -- "$rootfs"
}

scan_image control-plane "$CONTROL_IMAGE"
scan_image execution-worker "$WORKER_IMAGE"
scan_image python-execution "$PYTHON_EXECUTION_IMAGE"
scan_image node-execution "$NODE_EXECUTION_IMAGE"
