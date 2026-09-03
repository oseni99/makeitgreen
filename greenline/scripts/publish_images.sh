#!/bin/sh
set -eu

: "${SKOPEO_IMAGE:?SKOPEO_IMAGE is required}"
: "${REGISTRY_ROOT:?REGISTRY_ROOT is required}"
: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${ARCHIVE_DIR:?ARCHIVE_DIR is required}"
: "${AUTH_FILE:?AUTH_FILE is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"

case "$REGISTRY_ROOT" in
    ghcr.io/*/*) ;;
    *)
        echo "REGISTRY_ROOT must be a lowercase ghcr.io repository path" >&2
        exit 1
        ;;
esac
if printf '%s' "$REGISTRY_ROOT" | grep -q '[^a-z0-9./_-]'; then
    echo "REGISTRY_ROOT contains unsupported characters" >&2
    exit 1
fi
commit_sha=${SOURCE_TAG#sha-}
if [ "$commit_sha" = "$SOURCE_TAG" ] || [ "${#commit_sha}" -ne 40 ] || \
    printf '%s' "$commit_sha" | grep -q '[^0-9a-f]'; then
    echo "SOURCE_TAG must be sha- followed by a 40-character lowercase commit SHA" >&2
    exit 1
fi
for directory in "$ARCHIVE_DIR" "$OUTPUT_DIR"
do
    case "$directory" in
        /*) ;;
        *)
            echo "archive and output directories must be absolute" >&2
            exit 1
            ;;
    esac
done
case "$AUTH_FILE" in
    /*) ;;
    *)
        echo "AUTH_FILE must be absolute" >&2
        exit 1
        ;;
esac
if [ ! -f "$AUTH_FILE" ]; then
    echo "AUTH_FILE does not exist" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
: > "$OUTPUT_DIR/github-outputs"

for component in control-plane execution-worker python-execution node-execution
do
    archive="$ARCHIVE_DIR/$component.oci.tar"
    if [ ! -f "$archive" ]; then
        echo "missing OCI archive: $archive" >&2
        exit 1
    fi
    destination="$REGISTRY_ROOT-$component:$SOURCE_TAG"
    expected=$(docker run --rm \
        --mount "type=bind,src=$ARCHIVE_DIR,dst=/artifacts,readonly" \
        "$SKOPEO_IMAGE" inspect --format '{{.Digest}}' \
        "oci-archive:/artifacts/$component.oci.tar")
    expected_hex=${expected#sha256:}
    if [ "$expected_hex" = "$expected" ] || [ "${#expected_hex}" -ne 64 ] || \
        printf '%s' "$expected_hex" | grep -q '[^0-9a-f]'; then
        echo "could not resolve an OCI digest for $archive" >&2
        exit 1
    fi

    if existing=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$destination" 2>/dev/null); then
        if [ "$existing" != "$expected" ]; then
            echo "refusing to overwrite immutable tag $destination" >&2
            exit 1
        fi
    else
        docker run --rm \
            --mount "type=bind,src=$ARCHIVE_DIR,dst=/artifacts,readonly" \
            --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
            "$SKOPEO_IMAGE" copy --all --preserve-digests --retry-times 3 \
            --dest-authfile /auth/config.json \
            "oci-archive:/artifacts/$component.oci.tar" \
            "docker://$destination"
    fi

    actual=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$destination")
    if [ "$actual" != "$expected" ]; then
        echo "published digest does not match scanned archive for $component" >&2
        exit 1
    fi
    key=$(printf '%s' "$component" | tr '-' '_')
    printf '%s_digest=%s\n' "$key" "$actual" >> "$OUTPUT_DIR/github-outputs"
done

printf 'registry_root=%s\n' "$REGISTRY_ROOT" >> "$OUTPUT_DIR/github-outputs"
