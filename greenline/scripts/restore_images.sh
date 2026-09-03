#!/bin/sh
set -eu

: "${SKOPEO_IMAGE:?SKOPEO_IMAGE is required}"
: "${REGISTRY_ROOT:?REGISTRY_ROOT is required}"
: "${TARGET_TAG:?TARGET_TAG is required}"
: "${AUTH_FILE:?AUTH_FILE is required}"
: "${PROMOTION_RECORD:?PROMOTION_RECORD is required}"
: "${ROLLBACK_RECORD:?ROLLBACK_RECORD is required}"

case "$REGISTRY_ROOT" in ghcr.io/*/*) ;; *) exit 1 ;; esac
if printf '%s' "$REGISTRY_ROOT" | grep -q '[^a-z0-9./_-]'; then
    echo "REGISTRY_ROOT contains unsupported characters" >&2
    exit 1
fi
case "$TARGET_TAG" in staging|production) ;; *) exit 1 ;; esac
case "$AUTH_FILE:$PROMOTION_RECORD:$ROLLBACK_RECORD" in
    /*:/*:/*) ;;
    *) echo "rollback paths must be absolute" >&2; exit 1 ;;
esac
[ -f "$AUTH_FILE" ] || { echo "AUTH_FILE does not exist" >&2; exit 1; }
[ -f "$PROMOTION_RECORD" ] || { echo "PROMOTION_RECORD does not exist" >&2; exit 1; }

tab=$(printf '\t')
line_number=1
for expected_component in control-plane execution-worker python-execution node-execution
do
    line=$(sed -n "${line_number}p" "$PROMOTION_RECORD")
    IFS="$tab" read -r component previous_digest promoted_digest <<EOF
$line
EOF
    previous_hex=${previous_digest#sha256:}
    promoted_hex=${promoted_digest#sha256:}
    if [ "$component" != "$expected_component" ] || \
        [ "${#previous_hex}" -ne 64 ] || [ "${#promoted_hex}" -ne 64 ] || \
        printf '%s%s' "$previous_hex" "$promoted_hex" | grep -q '[^0-9a-f]'; then
        echo "promotion record has no complete, valid rollback set" >&2
        exit 1
    fi
    line_number=$((line_number + 1))
done
[ "$(sed -n '5p' "$PROMOTION_RECORD")" = "" ] || {
    echo "promotion record contains unexpected components" >&2
    exit 1
}

# Refuse stale rollback evidence before making the first change.
line_number=1
for component in control-plane execution-worker python-execution node-execution
do
    line=$(sed -n "${line_number}p" "$PROMOTION_RECORD")
    IFS="$tab" read -r recorded_component previous_digest promoted_digest <<EOF
$line
EOF
    repository="$REGISTRY_ROOT-$component"
    target="$repository:$TARGET_TAG"
    current_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target")
    if [ "$current_digest" != "$promoted_digest" ] && \
        [ "$current_digest" != "$previous_digest" ]; then
        echo "refusing rollback because $component has an unrelated digest" >&2
        exit 1
    fi
    line_number=$((line_number + 1))
done

: > "$ROLLBACK_RECORD"
line_number=1
for component in control-plane execution-worker python-execution node-execution
do
    line=$(sed -n "${line_number}p" "$PROMOTION_RECORD")
    IFS="$tab" read -r recorded_component previous_digest promoted_digest <<EOF
$line
EOF
    repository="$REGISTRY_ROOT-$component"
    target="$repository:$TARGET_TAG"
    current_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target")
    if [ "$current_digest" = "$promoted_digest" ]; then
        docker run --rm \
            --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
            "$SKOPEO_IMAGE" copy --all --preserve-digests --retry-times 3 \
            --src-authfile /auth/config.json --dest-authfile /auth/config.json \
            "docker://$repository@$previous_digest" "docker://$target"
    elif [ "$current_digest" != "$previous_digest" ]; then
        echo "refusing rollback because $component changed after preflight" >&2
        exit 1
    fi
    restored_digest=$(docker run --rm \
        --mount "type=bind,src=$AUTH_FILE,dst=/auth/config.json,readonly" \
        "$SKOPEO_IMAGE" inspect --authfile /auth/config.json \
        --format '{{.Digest}}' "docker://$target")
    if [ "$restored_digest" != "$previous_digest" ]; then
        echo "automatic rollback changed the digest for $component" >&2
        exit 1
    fi
    printf '%s\t%s\t%s\n' "$component" "$promoted_digest" "$restored_digest" >> "$ROLLBACK_RECORD"
    line_number=$((line_number + 1))
done
