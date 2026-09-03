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

# The record is recovery evidence. Never replace evidence from an earlier partial
# attempt: doing so would record an already-promoted digest as the rollback target.
if [ -s "$RECORD_FILE" ]; then
    echo "RECORD_FILE already contains promotion evidence" >&2
    exit 1
fi

record_temp="${RECORD_FILE}.tmp.$$"
trap 'rm -f "$record_temp"' EXIT HUP INT TERM
: > "$record_temp"

# Resolve and validate the complete change set before moving the first mutable
# environment tag. A copy failure can then be recovered using the complete record.
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

    if previous_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target" 2>/dev/null); then
        previous_hex=${previous_digest#sha256:}
        if [ "$previous_hex" = "$previous_digest" ] || \
            [ "${#previous_hex}" -ne 64 ] || \
            printf '%s' "$previous_hex" | grep -q '[^0-9a-f]'; then
            echo "previous digest is invalid for $component" >&2
            exit 1
        fi
    else
        echo "target tag has no rollback digest for $component" >&2
        exit 1
    fi

    printf '%s\t%s\t%s\n' \
        "$component" "$previous_digest" "$source_digest" >> "$record_temp"
done

mv "$record_temp" "$RECORD_FILE"
trap - EXIT HUP INT TERM

tab=$(printf '\t')
line_number=1
for component in control-plane execution-worker python-execution node-execution
do
    line=$(sed -n "${line_number}p" "$RECORD_FILE")
    IFS="$tab" read -r recorded_component previous_digest source_digest <<EOF
$line
EOF
    if [ "$recorded_component" != "$component" ]; then
        echo "promotion record changed after preflight" >&2
        exit 1
    fi
    repository="$REGISTRY_ROOT-$component"
    target="$repository:$TARGET_TAG"
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
    line_number=$((line_number + 1))
done
