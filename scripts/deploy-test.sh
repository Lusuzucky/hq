#!/usr/bin/env bash
# Test deploy — deploys only files changed by this branch, with rollback.
#   bash scripts/deploy-test.sh           # deploy changed files
#   bash scripts/deploy-test.sh --rollback # restore original state
#
# File list is auto-detected from git: anything modified or added under
# hermes/modified/ or plugins/ since branching from main.
# No manual FILES array needed.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"
BACKUP_DIR="/tmp/hermes-deploy-backup"

# ── Path mapping ───────────────────────────────────────
# Each entry: "repo_pattern|target_path"
# pc_utils.py is special: deployed to multiple targets
map_targets() {
    local src="$1"
    case "$src" in
        hermes/modified/hermes_state.py)
            echo "$HERMES_DIR/hermes_state.py" ;;
        hermes/modified/tools/*)
            echo "$HERMES_DIR/tools/$(basename "$src")" ;;
        hermes/modified/gateway/run.py)
            echo "$HERMES_DIR/gateway/run.py" ;;
        hermes/modified/gateway/session.py)
            echo "$HERMES_DIR/gateway/session.py" ;;
        hermes/modified/gateway/platforms/base.py)
            echo "$HERMES_DIR/gateway/platforms/base.py" ;;
        hermes/modified/gateway/platforms/qqbot/*)
            echo "$HERMES_DIR/gateway/platforms/qqbot/$(basename "$src")" ;;
        plugins/gptsovits/*)
            echo "$PROFILE_DIR/plugins/tts/gptsovits/$(basename "$src")" ;;
        plugins/comfyui/*)
            echo "$PROFILE_DIR/plugins/image_gen/comfyui/$(basename "$src")" ;;
        plugins/pc_utils.py)
            echo "$PROFILE_DIR/plugins/tts/pc_utils.py"
            echo "$PROFILE_DIR/plugins/image_gen/pc_utils.py" ;;
        *)  ;;  # unknown → skip
    esac
}

# ── Rollback ───────────────────────────────────────────
if [[ "${1:-}" == "--rollback" ]]; then
    if [ ! -d "$BACKUP_DIR" ]; then
        echo "No backup found."
        exit 1
    fi
    echo "=== Rolling back ==="

    for f in "$BACKUP_DIR"/*; do
        [ -f "$f" ] || continue
        local bn=$(basename "$f")
        [ "$bn" = ".new_files" ] || [ "$bn" = ".manifest" ] && continue
        while IFS='|' read -r bname target; do
            [ "$bname" = "$bn" ] || continue
            cp "$f" "$target"
            echo "  restored: $target"
        done < "$BACKUP_DIR/.manifest"
    done

    if [ -f "$BACKUP_DIR/.new_files" ]; then
        while IFS='|' read -r name target; do
            rm -f "$target"
            echo "  removed (was new): $target"
        done < "$BACKUP_DIR/.new_files"
    fi

    rm -rf "$BACKUP_DIR"
    hermes gateway restart -p gf
    echo "=== Rollback complete ==="
    exit 0
fi

# ── Deploy ─────────────────────────────────────────────
declare -a ENTRIES=()
while IFS= read -r f; do
    [ -n "$f" ] || continue
    while IFS= read -r target; do
        [ -n "$target" ] || continue
        ENTRIES+=("$f|$target")
    done < <(map_targets "$f")
done < <(git -C "$REPO_DIR" diff --name-only "main...HEAD" -- hermes/modified/ plugins/)

if [ ${#ENTRIES[@]} -eq 0 ]; then
    echo "No changed files detected."
    exit 0
fi

mkdir -p "$BACKUP_DIR"

echo "=== Test deploy ==="
echo "→ Changed files (git diff main...HEAD):"
for entry in "${ENTRIES[@]}"; do
    echo "    ${entry%%|*}  →  ${entry##*|}"
done

for entry in "${ENTRIES[@]}"; do
    src="$REPO_DIR/${entry%%|*}"
    target="${entry##*|}"
    name="$(basename "$target")"

    # Track for rollback
    echo "$name|$target" >> "$BACKUP_DIR/.manifest"

    # Back up once — never overwrite first backup
    if [ ! -f "$BACKUP_DIR/$name" ] && ! grep -q "^$name|$target$" "$BACKUP_DIR/.new_files" 2>/dev/null; then
        if [ -f "$target" ]; then
            cp "$target" "$BACKUP_DIR/$name"
        else
            echo "$name|$target" >> "$BACKUP_DIR/.new_files"
        fi
    fi

    cp "$src" "$target"
    echo "  deployed: $target"
done

hermes gateway restart -p gf
echo "=== Done ==="
echo "Rollback: bash scripts/deploy-test.sh --rollback"
