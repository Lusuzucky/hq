#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['tool_input']['command'])")

# --- SSH handling ---
if ! echo "$COMMAND" | grep -qE '^ssh[[:space:]]'; then
  exit 0
fi

# Strip ssh [flags] [user@]host, leaving the remote command
REMOTE_CMD=$(echo "$COMMAND" | sed -E 's/^ssh[[:space:]]+(-[^[:space:]]+[[:space:]]+)*([^[:space:]]+@)?[^[:space:]]+[[:space:]]+//')

# If nothing left, it's interactive login -> allow
if [ -z "$REMOTE_CMD" ] || [ "$REMOTE_CMD" = "$COMMAND" ]; then
  exit 0
fi

# Strip outer quotes around the remote command
REMOTE_CMD="${REMOTE_CMD#\"}"; REMOTE_CMD="${REMOTE_CMD%\"}"
REMOTE_CMD="${REMOTE_CMD#\'}"; REMOTE_CMD="${REMOTE_CMD%\'}"

# --- Modification patterns — checked first, if matched -> block ---
MODIFY_PATTERNS=(
  # Direct file editing
  '(^|[[:space:];|&])(vi|vim|nano|emacs|ed|pico|micro|helix)([[:space:]]|$)'
  # sed/awk in-place or with redirect
  'sed[[:space:]].*-i([[:space:]]|$)'
  'sed[[:space:]].*([[:space:]]>|>>)'
  'awk[[:space:]].*([[:space:]]>|>>)'
  # echo/printf/cat redirect to file
  '(echo|printf)[[:space:]].*([[:space:]]>|>>)'
  'cat[[:space:]].*([[:space:]]>|>>)'
  'tee[[:space:]]'
  'dd[[:space:]].*of='
  # File operations
  '(^|[[:space:];|&])rm[[:space:]]'
  '(^|[[:space:];|&])mv[[:space:]]'
  '(^|[[:space:];|&])cp[[:space:]]'
  '(^|[[:space:];|&])chmod[[:space:]]'
  '(^|[[:space:];|&])chown[[:space:]]'
  '(^|[[:space:];|&])touch[[:space:]]'
  '(^|[[:space:];|&])mkdir[[:space:]]'
  'ln[[:space:]]+-[sf]'
  # Git write operations
  'git[[:space:]]+(add|commit|checkout|merge|rebase|reset|branch[[:space:]]+-[dD]|push)'
  # Package management
  '(apt|yum|dnf|pacman|zypper)[[:space:]]'
  'pip[[:space:]]*install|npm[[:space:]]*install'
  # Service management
  'systemctl[[:space:]]+(start|stop|restart|enable|disable|mask|daemon-reload)'
  # Container write ops
  'docker[[:space:]]+(rm|rmi|stop|start|restart|exec|run|build|compose[[:space:]]+up)'
  'kubectl[[:space:]]+(apply|delete|edit|patch|scale|rollout|exec)'
)

for pattern in "${MODIFY_PATTERNS[@]}"; do
  if echo "$REMOTE_CMD" | grep -qE "$pattern"; then
    echo "BLOCKED: remote file modification via SSH is not allowed." >&2
    echo "  Command: ssh ... $REMOTE_CMD" >&2
    echo "  Use this workflow instead:" >&2
    echo "    1. scp user@host:/path/file ./local-copy" >&2
    echo "    2. Edit local-copy with tools" >&2
    echo "    3. scp ./local-copy user@host:/path/file" >&2
    exit 2
  fi
done

exit 0
