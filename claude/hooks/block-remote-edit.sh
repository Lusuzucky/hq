#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# --- SCP handling ---
if echo "$COMMAND" | grep -qE '^scp[[:space:]]'; then
  # Extract non-flag arguments (skip -r, -P, -i, -o, -q, -v, -C, -p, -l etc.)
  ARGS=()
  IFS=' ' read -ra TOKENS <<< "$COMMAND"
  for tok in "${TOKENS[@]}"; do
    if [[ "$tok" != -* ]] && [ "$tok" != "scp" ]; then
      ARGS+=("$tok")
    fi
  done

  REMOTE_PATTERN='[^@]+@[^:]+:|^[^@]+:'

  # Find remote positions
  REMOTE_POS=()
  for i in "${!ARGS[@]}"; do
    if echo "${ARGS[$i]}" | grep -qE "$REMOTE_PATTERN"; then
      REMOTE_POS+=("$i")
    fi
  done

  LAST_IDX=$((${#ARGS[@]} - 1))

  # If last arg is remote → pull (allowed)
  if [[ "${#REMOTE_POS[@]}" -eq 1 ]] && [[ "${REMOTE_POS[0]}" -eq "$LAST_IDX" ]]; then
    exit 0
  fi

  # Otherwise → push (or remote-to-remote), require confirmation
  echo "BLOCKED: scp push requires explicit confirmation." >&2
  echo "  Command: $COMMAND" >&2
  echo "  Re-run with approval if you intend to push files to remote." >&2
  exit 2
fi

# --- SSH handling ---
if ! echo "$COMMAND" | grep -qE '^ssh[[:space:]]'; then
  exit 0
fi

# Not a concern if no remote command is being run (interactive login)
HAS_CMD=$(echo "$COMMAND" | grep -oP 'ssh\s+(?:-[^\s]+\s+)*([^\s]+@)?[^\s]+\s+(.+)' | head -1)
if [ -z "$HAS_CMD" ]; then
  exit 0
fi

REMOTE_CMD=$(echo "$COMMAND" | sed -E 's/^ssh\s+(-[^\s]+\s+)*([^\s]+@)?[^\s]+\s+//')

# Read-only patterns — allowed
READONLY_PATTERNS=(
  '^(cat|less|more|head|tail|zcat|zgrep|bzcat)\b'
  '^grep\b(?!.*>)'
  '^ls\b'
  '^find\b(?!.*-exec.*rm)'
  '^ps\b|^top\b|^htop\b'
  '^df\b|^du\b|^free\b|^uptime\b'
  '^systemctl\s+(status|list|is-enabled|is-active|show)\b'
  '^journalctl\b'
  '^docker\s+(ps|logs|inspect|images|stats)\b'
  '^kubectl\s+(get|describe|logs)\b'
  '^who\b|^w\b|^id\b|^groups\b'
  '^which\b|^type\b|^command\b'
  '^echo\b(?!.*>)'
  '^date\b|^hostname\b|^uname\b'
  '^true\b|^false\b'
  '^test\b|^\[\b'
)

# Modification patterns — blocked
MODIFY_PATTERNS=(
  '\bsed\b(?!.*-n\b)[^>]*(-i|>|>>)'
  '\bawk\b.*>'
  '\becho\b.*>'
  '\bprintf\b.*>'
  '\btee\b'
  '(^|\s)(vim?|nano|emacs|ed|pico|micro|helix)\s'
  '\bdd\b.*of='
  '\bcat\b.*>'
  '\brm\b'
  '\bmv\b'
  '\bcp\b(?!.*\./)'
  '\bchmod\b'
  '\bchown\b'
  '\btouch\b'
  '\bmkdir\b'
  '\bln\s+-'
  '\bgit\s+(add|commit|checkout|merge|rebase|reset)'
  '\bgit\s+branch\s+-[dD]'
  '\bgit\s+push\b'
  '\binstall\b'
  '\bapt\b|\byum\b|\bdnf\b|\bpacman\b|\bzypper\b'
  '\bpip\b.*install|\bnpm\b.*install'
  '\bsystemctl\s+(start|stop|restart|enable|disable|mask)\b'
  '\bdocker\s+(rm|rmi|stop|start|restart|exec|run|build|compose\s+up)'
  '\bkubectl\s+(apply|delete|edit|patch|scale|rollout|exec)'
)

for pattern in "${READONLY_PATTERNS[@]}"; do
  if echo "$REMOTE_CMD" | grep -qE "$pattern"; then
    exit 0
  fi
done

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
