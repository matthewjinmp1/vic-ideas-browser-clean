#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || true)"
fi
if [ -z "$PYTHON" ]; then
  echo -e "${RED}Could not find Python. Install Python 3 or create .venv before running tests.${NC}"
  exit 1
fi

CODEX_NODE_DIR="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin"
if [ -d "$CODEX_NODE_DIR" ]; then
  export PATH="$CODEX_NODE_DIR:$PATH"
fi

run_step() {
  local label="$1"
  shift
  echo -e "${YELLOW}${label}${NC}"
  "$@"
  echo -e "${GREEN}${label} passed${NC}"
  echo
}

echo -e "${YELLOW}Running local VIC test suite from $ROOT_DIR${NC}"
echo

run_step "Python return calculation tests" \
  "$PYTHON" -m unittest api.tests.test_return_calculations -v

run_step "Forward beat calculator CLI smoke test" \
  "$PYTHON" scripts/calculate_forward_beats.py --forward-quarters 4

FRONTEND_BIN="$ROOT_DIR/frontend/node_modules/.bin"
if [ ! -d "$FRONTEND_BIN" ]; then
  echo -e "${RED}frontend/node_modules is missing. Run npm install in frontend first.${NC}"
  exit 1
fi

run_step "Frontend TypeScript check" \
  bash -c 'cd "$1" && "$2" --noEmit' bash "$ROOT_DIR/frontend" "$FRONTEND_BIN/tsc"

run_step "Frontend production build" \
  bash -c 'cd "$1" && "$2" build' bash "$ROOT_DIR/frontend" "$FRONTEND_BIN/vite"

echo -e "${GREEN}All local tests passed.${NC}"
