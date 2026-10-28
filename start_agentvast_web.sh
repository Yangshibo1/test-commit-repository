#!/bin/bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${1:-$REPOSITORY_ROOT/VAST_Challenge_2026_MC2}"
PYTHON_BIN="$REPOSITORY_ROOT/.venv/bin/python"
CLAUDE_COMMAND="$REPOSITORY_ROOT/claude_ccs.sh"
NODE_BIN="/Users/bytedance/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing project virtual environment: $PYTHON_BIN" >&2
  exit 1
fi
if [[ ! -d "$REPOSITORY_ROOT/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies" >&2
  exit 2
fi
if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project directory does not exist: $PROJECT_DIR" >&2
  exit 3
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

cd "$REPOSITORY_ROOT"
PATH="$REPOSITORY_ROOT/.venv/bin:$HOME/.local/bin:$PATH" \
  "$PYTHON_BIN" -m agentvast.cli web \
  --project "$PROJECT_DIR" \
  --host 127.0.0.1 \
  --port 8765 \
  --claude-command "$CLAUDE_COMMAND" &
BACKEND_PID=$!

cd "$REPOSITORY_ROOT/frontend"
"$NODE_BIN" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 3000 &
FRONTEND_PID=$!

echo "AgentVAST backend: http://127.0.0.1:8765"
echo "AgentVAST frontend: http://127.0.0.1:3000"
wait
