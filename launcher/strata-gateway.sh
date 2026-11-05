#!/usr/bin/env bash
# strata-gateway.sh - start the Strata gateway on Linux/macOS.
# Point GW_HOME (or STRATA_HOME) at your Strata engine root - the folder that
# holds serve/server.py and its .venv. Nothing personal is hardcoded.
set -euo pipefail

GW_HOME="${GW_HOME:-$HOME/Strata}"
export STRATA_HOME="${STRATA_HOME:-$GW_HOME}"

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROUTER="$HERE/strata-router.py"
PY="${STRATA_PYTHON:-$STRATA_HOME/.venv/bin/python}"

if [ ! -f "$ROUTER" ]; then
  echo "[launcher] gateway entry not found: $ROUTER  未找到网关入口" >&2
  exit 1
fi
if [ ! -x "$PY" ]; then
  echo "[launcher] Strata python not found: $PY - set STRATA_PYTHON or fix GW_HOME" >&2
  exit 1
fi
exec "$PY" "$ROUTER"
