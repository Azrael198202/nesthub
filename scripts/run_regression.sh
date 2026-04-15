#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ -x "$VENV_PYTHON" ]]; then
  PYTHON_CMD="$VENV_PYTHON"
else
  PYTHON_CMD="python3"
fi

cd "$ROOT_DIR"

"$PYTHON_CMD" -m pytest -q \
  test/test_model_router_runtime.py \
  test/test_workflow_executor_runtime.py \
  test/test_core_engine_runtime.py \
  test/test_core_engine_agent_runtime.py
