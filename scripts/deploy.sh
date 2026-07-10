#!/usr/bin/env bash
# Deploy Hermes modifications from homelab repo to live Hermes installation.
# Run from the repo root on the server.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"

echo "=== Deploying from $REPO_DIR ==="

# ── Hermes source files ──────────────────────────────────────────
echo "→ Copying modified source files..."

# adapter.py (QQ platform adapter)
cp "$REPO_DIR/hermes/modified/gateway/platforms/qqbot/adapter.py" \
   "$HERMES_DIR/gateway/platforms/qqbot/adapter.py"

# base.py (base platform adapter)
cp "$REPO_DIR/hermes/modified/gateway/platforms/base.py" \
   "$HERMES_DIR/gateway/platforms/base.py"

# send_message_tool.py
cp "$REPO_DIR/hermes/modified/tools/send_message_tool.py" \
   "$HERMES_DIR/tools/send_message_tool.py"

# tts_tool.py
cp "$REPO_DIR/hermes/modified/tools/tts_tool.py" \
   "$HERMES_DIR/tools/tts_tool.py"

# hermes_state.py
cp "$REPO_DIR/hermes/modified/hermes_state.py" \
   "$HERMES_DIR/hermes_state.py"

# session.py
cp "$REPO_DIR/hermes/modified/gateway/session.py" \
   "$HERMES_DIR/gateway/session.py"

# run.py
cp "$REPO_DIR/hermes/modified/gateway/run.py" \
   "$HERMES_DIR/gateway/run.py"

# ── Config files ─────────────────────────────────────────────────
echo "→ Copying config files..."
cp "$REPO_DIR/hermes/config/config.yaml" "$PROFILE_DIR/config.yaml"
cp "$REPO_DIR/hermes/config/honcho.json" "$PROFILE_DIR/honcho.json"

# ── Skills ───────────────────────────────────────────────────────
if [ -d "$REPO_DIR/hermes/skills" ] && [ "$(ls -A "$REPO_DIR/hermes/skills" 2>/dev/null)" ]; then
    echo "→ Copying skills..."
    cp -r "$REPO_DIR/hermes/skills/"* "$PROFILE_DIR/skills/"
fi

# ── Plugins ──────────────────────────────────────────────────────
if [ -d "$REPO_DIR/plugins" ] && [ "$(ls -A "$REPO_DIR/plugins" 2>/dev/null)" ]; then
    echo "→ Copying plugins..."
    # pc_utils.py goes to each plugin directory that needs it
    for dir in image_gen tts; do
        if [ -f "$REPO_DIR/plugins/pc_utils.py" ]; then
            cp "$REPO_DIR/plugins/pc_utils.py" "$PROFILE_DIR/plugins/$dir/pc_utils.py"
        fi
    done
    if [ -d "$REPO_DIR/plugins/comfyui" ]; then
        cp -r "$REPO_DIR/plugins/comfyui/"* "$PROFILE_DIR/plugins/image_gen/comfyui/"
    fi
    if [ -d "$REPO_DIR/plugins/gptsovits" ]; then
        cp -r "$REPO_DIR/plugins/gptsovits/"* "$PROFILE_DIR/plugins/tts/gptsovits/"
    fi
fi

# ── Restart gateway ──────────────────────────────────────────────
echo "→ Restarting gateway..."
hermes gateway restart -p gf

echo "=== Deploy complete ==="
