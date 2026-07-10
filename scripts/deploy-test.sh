#!/usr/bin/env bash
# Test deploy with auto-backup and rollback.
#   bash scripts/deploy-test.sh           # deploy + backup
#   bash scripts/deploy-test.sh --rollback # restore latest backup
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"
BACKUP_DIR="/tmp/hermes-deploy-backup"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── Files to deploy ────────────────────────────────────
# Each entry: "source_relative_to_REPO_DIR|target_full_path"
FILES=(
    "hermes/modified/tools/tts_tool.py|$HERMES_DIR/tools/tts_tool.py"
    "plugins/gptsovits/__init__.py|$PROFILE_DIR/plugins/tts/gptsovits/__init__.py"
    "plugins/gptsovits/plugin.yaml|$PROFILE_DIR/plugins/tts/gptsovits/plugin.yaml"
    "plugins/pc_utils.py|$PROFILE_DIR/plugins/tts/pc_utils.py"
)

# ── Rollback ───────────────────────────────────────────
if [[ "${1:-}" == "--rollback" ]]; then
    LATEST=$(ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | sort | tail -1)
    if [ -z "$LATEST" ]; then
        echo "No backup found in $BACKUP_DIR"
        exit 1
    fi
    echo "=== Rolling back to $LATEST ==="
    for entry in "${FILES[@]}"; do
        TARGET="${entry##*|}"
        BACKUP_FILE="$LATEST/$(basename "$TARGET")"
        if [ -f "$BACKUP_FILE" ]; then
            cp "$BACKUP_FILE" "$TARGET"
            echo "  restored: $TARGET"
        fi
    done
    hermes gateway restart -p gf
    echo "=== Rollback complete ==="
    exit 0
fi

# ── Deploy ─────────────────────────────────────────────
THIS_BACKUP="$BACKUP_DIR/$TIMESTAMP"
mkdir -p "$THIS_BACKUP"

echo "=== Test deploy: TTS emotion ==="
echo "→ Backup: $THIS_BACKUP"

for entry in "${FILES[@]}"; do
    SOURCE="$REPO_DIR/${entry%%|*}"
    TARGET="${entry##*|}"

    # Backup existing file
    if [ -f "$TARGET" ]; then
        cp "$TARGET" "$THIS_BACKUP/$(basename "$TARGET")"
    fi

    cp "$SOURCE" "$TARGET"
    echo "  deployed: $TARGET"
done

hermes gateway restart -p gf
echo "=== Done ==="
echo "Rollback: bash scripts/deploy-test.sh --rollback"
