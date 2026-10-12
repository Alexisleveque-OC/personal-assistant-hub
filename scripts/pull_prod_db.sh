#!/bin/sh
set -e

# ==============================================================================
# Script de rapatriement rapide de la base de données de production vers le local
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/pull_prod_db.py" "$@"
