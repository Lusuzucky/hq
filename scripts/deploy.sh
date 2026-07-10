#!/usr/bin/env bash
# Full deploy — copies ALL files from hermes/modified/, plugins/, and config
# to the live Hermes installation. Use after a successful merge to main.
#   bash scripts/deploy.sh
set -euo pipefail

# Guard: full deploy is only allowed from main.
# Use deploy-test.sh for feature-branch deployments.
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "ERROR: full deploy only allowed from main branch (current: $CURRENT_BRANCH)" >&2
    echo "Use bash scripts/deploy-test.sh for feature-branch deployments." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"

# Shared mapping — keep in sync with deploy-test.sh
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

echo "=== Full deploy ==="

# Find all files under hermes/modified/ and plugins/
while IFS= read -r -d '' f; do
    # Strip REPO_DIR prefix for relative-path matching
    rel="${f#$REPO_DIR/}"
    while IFS= read -r target; do
        [ -n "$target" ] || continue
        mkdir -p "$(dirname "$target")"
        cp "$f" "$target"
        echo "  deployed: $target"
    done < <(map_targets "$rel")
done < <(find "$REPO_DIR/hermes/modified" "$REPO_DIR/plugins" -type f -not -path '*/__pycache__/*' -print0)

# Config
if [ -f "$REPO_DIR/hermes/config/config.yaml" ]; then
    cp "$REPO_DIR/hermes/config/config.yaml" "$PROFILE_DIR/config.yaml"
    echo "  deployed: config.yaml"
fi
if [ -f "$REPO_DIR/hermes/config/honcho.json" ]; then
    cp "$REPO_DIR/hermes/config/honcho.json" "$PROFILE_DIR/honcho.json"
    echo "  deployed: honcho.json"
fi

# Skills
if [ -d "$REPO_DIR/hermes/skills" ] && [ "$(ls -A "$REPO_DIR/hermes/skills" 2>/dev/null)" ]; then
    cp -r "$REPO_DIR/hermes/skills/"* "$PROFILE_DIR/skills/"
    echo "  deployed: skills/"
fi

hermes gateway restart -p gf
echo "=== Full deploy complete ==="
