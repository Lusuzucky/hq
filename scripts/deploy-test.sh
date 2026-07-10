#!/usr/bin/env bash
# Test deploy with auto-backup and rollback.
#   bash scripts/deploy-test.sh           # deploy (first run creates backup)
#   bash scripts/deploy-test.sh --rollback # restore original files
#
# Only the *first* run creates backups — subsequent runs won't overwrite them,
# so rollback always restores the original pre-deploy state.
#
# ⚠️  Edit FILES array below to list only your branch's changes.
#     Revert this file to main's template before merging the PR:
#       git checkout main -- scripts/deploy-test.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"
BACKUP_DIR="/tmp/hermes-deploy-backup"

# ── Edit this: add one entry per file your branch touches ──
# Format: "source_relative_to_REPO_DIR|target_full_path"
FILES=(
    # "hermes/modified/gateway/platforms/qqbot/adapter.py|$HERMES_DIR/gateway/platforms/qqbot/adapter.py"
)

# ── Rollback ───────────────────────────────────────────
if [[ "${1:-}" == "--rollback" ]]; then
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
        echo "No backup found in $BACKUP_DIR"
        exit 1
    fi
    echo "=== Rolling back ==="
    for entry in "${FILES[@]}"; do
        TARGET="${entry##*|}"
        BACKUP_FILE="$BACKUP_DIR/$(basename "$TARGET")"
        if [ -f "$BACKUP_FILE" ]; then
            cp "$BACKUP_FILE" "$TARGET"
            echo "  restored: $TARGET"
        elif grep -qxF "$TARGET" "$BACKUP_DIR/.new_files" 2>/dev/null; then
            rm -f "$TARGET"
            echo "  removed (was new): $TARGET"
        else
            echo "  skipped (no backup): $TARGET"
        fi
    done
    hermes gateway restart -p gf
    echo "=== Rollback complete ==="
    exit 0
fi

# ── Deploy ─────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

echo "=== Test deploy ==="

for entry in "${FILES[@]}"; do
    SOURCE="$REPO_DIR/${entry%%|*}"
    TARGET="${entry##*|}"
    BACKUP_FILE="$BACKUP_DIR/$(basename "$TARGET")"

    # Only back up the *first* time — never overwrite the original backup
    if [ ! -f "$BACKUP_FILE" ] && ! grep -qxF "$TARGET" "$BACKUP_DIR/.new_files" 2>/dev/null; then
        if [ -f "$TARGET" ]; then
            cp "$TARGET" "$BACKUP_FILE"
            echo "  backed up: $TARGET"
        else
            echo "$TARGET" >> "$BACKUP_DIR/.new_files"
            echo "  new file: $TARGET"
        fi
    fi

    cp "$SOURCE" "$TARGET"
    echo "  deployed: $TARGET"
done

hermes gateway restart -p gf
echo "=== Done ==="
echo "Rollback: bash scripts/deploy-test.sh --rollback"
