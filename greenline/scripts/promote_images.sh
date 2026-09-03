#!/bin/sh
set -eu

: "${SKOPEO_IMAGE:?SKOPEO_IMAGE is required}"
: "${REGISTRY_ROOT:?REGISTRY_ROOT is required}"
: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${TARGET_TAG:?TARGET_TAG is required}"
: "${OPERATION:?OPERATION is required}"
: "${AUTH_FILE:?AUTH_FILE is required}"
: "${RECORD_FILE:?RECORD_FILE is required}"

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
    echo "SOURCE_TAG must identify an immutable commit release" >&2
    exit 1
fi
case "$TARGET_TAG" in
    staging|production) ;;
    *)
        echo "TARGET_TAG must be staging or production" >&2
        exit 1
        ;;
esac
if [ ! -f "$AUTH_FILE" ]; then
    echo "AUTH_FILE does not exist" >&2
    exit 1
fi
case "$OPERATION" in
    promote|rollback) ;;
    *)
        echo "OPERATION must be promote or rollback" >&2
        exit 1
        ;;
esac
case "$AUTH_FILE" in
    /*) ;;
    *)
        echo "AUTH_FILE must be absolute" >&2
        exit 1
        ;;
esac
case "$RECORD_FILE" in
    /*) ;;
    *)
        echo "RECORD_FILE must be absolute" >&2
        exit 1
        ;;
esac

: > "$RECORD_FILE"
for component in control-plane execution-worker python-execution node-execution
do
    repository="$REGISTRY_ROOT-$component"
    source="$repository:$SOURCE_TAG"
    target="$repository:$TARGET_TAG"
    source_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$source")
    source_hex=${source_digest#sha256:}
    if [ "$source_hex" = "$source_digest" ] || [ "${#source_hex}" -ne 64 ] || \
        printf '%s' "$source_hex" | grep -q '[^0-9a-f]'; then
        echo "source digest is invalid for $component" >&2
        exit 1
    fi

    previous_digest=none
    if inspected=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target" 2>/dev/null); then
        previous_digest=$inspected
    fi

    docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" copy --all --preserve-digests --retry-times 3 \
        --src-authfile /auth/config.json --dest-authfile /auth/config.json \
        "docker://$repository@$source_digest" "docker://$target"

    promoted_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target")
    if [ "$promoted_digest" != "$source_digest" ]; then
        echo "promotion changed the digest for $component" >&2
        exit 1
    fi
    printf '%s\t%s\t%s\n' "$component" "$previous_digest" "$promoted_digest" >> "$RECORD_FILE"
done
