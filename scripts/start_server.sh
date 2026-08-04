#!/usr/bin/env bash
# Start Boltz2 web service
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="/home/pengpai/data/envs/boltz2/bin/python"
PORT="${PORT:-8765}"

export BOLTZ_CACHE="${BOLTZ_CACHE:-/home/pengpai/data/cache/boltz}"
export HF_HOME="${HF_HOME:-/home/pengpai/data/cache/huggingface}"
export TORCH_HOME="${TORCH_HOME:-/home/pengpai/data/cache/torch}"
export BOLTZ2_OUT_ROOT="${BOLTZ2_OUT_ROOT:-$ROOT/outputs}"

# Install web deps if missing
"$PY" -c "import fastapi, uvicorn" 2>/dev/null || \
  "$PY" -m pip install -q fastapi uvicorn pydantic

echo "Boltz2 Web: http://127.0.0.1:${PORT}"
echo "Output dir: $BOLTZ2_OUT_ROOT"
exec "$PY" -m uvicorn app.server:app --app-dir "$ROOT" --host 0.0.0.0 --port "$PORT"
