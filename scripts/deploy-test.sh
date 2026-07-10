#!/usr/bin/env bash
# Test deploy — only files changed by this branch.
# Run from the repo root on the server.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="/usr/local/lib/hermes-agent"
PROFILE_DIR="/root/.hermes/profiles/gf"

echo "=== Test deploy: TTS emotion ==="

cp "$REPO_DIR/hermes/modified/tools/tts_tool.py" "$HERMES_DIR/tools/tts_tool.py"
cp -r "$REPO_DIR/plugins/gptsovits/"* "$PROFILE_DIR/plugins/tts/gptsovits/"
cp "$REPO_DIR/plugins/pc_utils.py" "$PROFILE_DIR/plugins/tts/pc_utils.py"

hermes gateway restart -p gf

echo "=== Done ==="
