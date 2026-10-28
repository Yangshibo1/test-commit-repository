#!/bin/bash
set -euo pipefail

SESSION_ID="${1:-d04a523c-84b7-474f-a28f-b5b964d59ac9}"
REPOSITORY_ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$REPOSITORY_ROOT/.env"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
OBSERVATION_ROOT="${AGENTVAST_OBSERVER_ROOT:-$HOME/.agentvast/observations}"
SESSION_DIR="$OBSERVATION_ROOT/$SESSION_ID"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

API_KEY_LINE="$(grep -E '^AGENTVAST_SEMANTIC_API_KEY=' "$ENV_FILE" | tail -1 || true)"
API_KEY="${API_KEY_LINE#AGENTVAST_SEMANTIC_API_KEY=}"
if [[ -z "$API_KEY" || "$API_KEY" == "PASTE_YOUR_CCS_KEY_HERE" ]]; then
  echo "Set AGENTVAST_SEMANTIC_API_KEY in $ENV_FILE, then run this script again." >&2
  exit 2
fi

if [[ ! -d "$SESSION_DIR" ]]; then
  echo "Observer Session data is missing: $SESSION_DIR" >&2
  echo "Restore the Session directory there, or set AGENTVAST_OBSERVER_ROOT to its parent directory." >&2
  exit 3
fi

cd "$REPOSITORY_ROOT"

echo "Deriving Event Schema 2.0 for Session $SESSION_ID"
"$PYTHON_BIN" -m agentvast.cli observe derive "$SESSION_ID" --storage-root "$OBSERVATION_ROOT"

echo "Validating observation evidence"
"$PYTHON_BIN" -m agentvast.cli observe validate "$SESSION_ID" --storage-root "$OBSERVATION_ROOT"

echo "Starting semantic-workflow/0.4 model rebuild"
"$PYTHON_BIN" -m agentvast.cli observe semantic "$SESSION_ID" \
  --storage-root "$OBSERVATION_ROOT" \
  --force

echo "Rebuild complete: $SESSION_DIR/derived/semantic_workflow.json"
