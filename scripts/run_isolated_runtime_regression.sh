#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ -x "$VENV_PYTHON" ]] && "$VENV_PYTHON" -c "import pytest" >/dev/null 2>&1; then
  PYTHON_CMD="$VENV_PYTHON"
else
  PYTHON_CMD="python3"
fi

cd "$ROOT_DIR"

ARCHIVE_BASE="$ROOT_DIR/logs/generated_artifacts_archive"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_DIR="$ARCHIVE_BASE/$TIMESTAMP"
TRACE_DIR="$ROOT_DIR/nethub_runtime/generated/traces"

mkdir -p "$ARCHIVE_DIR"

if [[ -d "$TRACE_DIR" ]] && find "$TRACE_DIR" -maxdepth 1 -type f -name '*.json' | grep -q .; then
  mv "$TRACE_DIR"/*.json "$ARCHIVE_DIR"/
fi

echo "Archived existing generated traces to: $ARCHIVE_DIR"

"$PYTHON_CMD" -m pytest -q \
  test/test_family_member_agent_runtime.py \
  test/test_core_api.py \
  test/test_budget_scene_e2e_regression.py \
  test/test_semantic_memory_dashboard_api.py \
  test/test_semantic_memory_dashboard_static.py