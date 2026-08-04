#!/usr/bin/env bash
# Backfill pDockQ for jobs stuck at 0 or missing (uses boltz2 Python env).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/pengpai/data/envs/boltz2/bin/python}"
exec "$PY" "$ROOT/scripts/backfill_pdockq.py" "$@"
