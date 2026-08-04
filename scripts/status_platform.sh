#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT/logs"
PORT="${PORT:-8765}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

CELERY_GPU_COUNT="${CELERY_GPU_COUNT:-4}"

echo "=== BoltzFold status ==="
if [[ -f "$PID_DIR/api.pid" ]] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
  echo "API:    running (PID $(cat "$PID_DIR/api.pid"))"
else
  echo "API:    stopped"
fi

worker_up=0
for (( gpu=0; gpu<CELERY_GPU_COUNT; gpu++ )); do
  pid_file="$PID_DIR/celery-gpu${gpu}.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "GPU $gpu worker: running (PID $(cat "$pid_file"))"
    worker_up=$((worker_up + 1))
  else
    echo "GPU $gpu worker: stopped"
  fi
done
echo "GPU workers: $worker_up / $CELERY_GPU_COUNT running (unified fold+MD queue)"

curl -s "http://127.0.0.1:${PORT}/api/health" 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"HTTP:   {d.get('status','?')}  queue={d.get('queue_depth','?')}  running={d.get('running_jobs','?')}  workers={d.get('gpu_workers','?')}\")" \
  2>/dev/null || curl -s -o /dev/null -w "HTTP:   %{http_code} http://127.0.0.1:${PORT}/api/health\n" "http://127.0.0.1:${PORT}/api/health" 2>/dev/null || echo "HTTP:   unreachable"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo ""
  echo "=== GPU utilization ==="
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | \
    while IFS= read -r line; do echo "  $line"; done
fi
