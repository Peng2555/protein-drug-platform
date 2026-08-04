#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT/logs"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

CELERY_GPU_COUNT="${CELERY_GPU_COUNT:-4}"

stop_pid() {
  local name=$1 file=$2
  if [[ -f "$file" ]]; then
    local pid
    pid=$(cat "$file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null && echo "  $name stopped (PID $pid)" || true
    fi
    rm -f "$file"
  fi
}

echo "Stopping BoltzFold..."
stop_pid "API" "$PID_DIR/api.pid"
for (( gpu=0; gpu<CELERY_GPU_COUNT; gpu++ )); do
  stop_pid "GPU worker $gpu" "$PID_DIR/celery-gpu${gpu}.pid"
done
for pid_file in "$PID_DIR"/celery-md*.pid; do
  [[ -f "$pid_file" ]] || continue
  stop_pid "Legacy MD worker" "$pid_file"
done
stop_pid "Worker (legacy)" "$PID_DIR/celery.pid"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "celery -A app.celery_app worker" 2>/dev/null || true
echo "Done."
