#!/bin/bash
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"

if [[ ! -x "$CLAUDE_BIN" ]]; then
  echo "Claude executable not found: $CLAUDE_BIN" >&2
  exit 1
fi

# Claude reads the current settings.json written by CC Switch on every launch.
# Keep the project's semantic-provider .env separate from the interactive CLI.
export CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1

exec "$CLAUDE_BIN" "$@"
