#!/usr/bin/env bash
# Start BoltzFold in background (API + Celery). Safe to close terminal after run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/pengpai/data/envs/boltz2/bin/python}"
PORT="${PORT:-8765}"
LOG_DIR="$ROOT/logs"
PID_DIR="$LOG_DIR"

cd "$ROOT"
mkdir -p "$LOG_DIR"

# shellcheck disable=SC1091
[[ -f "$ROOT/scripts/docker_rootless.env" ]] && source "$ROOT/scripts/docker_rootless.env"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

CELERY_GPU_COUNT="${CELERY_GPU_COUNT:-4}"
CELERY_GPU_QUEUE="${CELERY_GPU_QUEUE:-gpu}"

export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export HMMER_PATH="${HMMER_PATH:-/home/pengpai/data/envs/IgGM/bin}"
export GMX_BIN="${GMX_BIN:-/home/pengpai/data/envs/IgGM/bin/gmx}"
export GEMMI_PY="${GEMMI_PY:-/home/pengpai/data/envs/IgGM/bin/python}"

"$PY" -c "import fastapi, celery, sqlalchemy" 2>/dev/null || \
  "$PY" -m pip install -q -r "$ROOT/requirements-platform.txt"

echo "=== Init DB ==="
"$PY" "$ROOT/scripts/init_db.py"

start_gpu_workers() {
  if [[ -f "$PID_DIR/celery.pid" ]]; then
    legacy_pid="$(cat "$PID_DIR/celery.pid")"
    if kill -0 "$legacy_pid" 2>/dev/null; then
      echo "Stopping legacy Celery worker (PID $legacy_pid)..."
      kill "$legacy_pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$PID_DIR/celery.pid"
  fi

  # Stop legacy separate MD workers if present
  for pid_file in "$PID_DIR"/celery-md*.pid; do
    [[ -f "$pid_file" ]] || continue
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping legacy MD worker (PID $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  done

  echo "=== Start GPU workers (queue=${CELERY_GPU_QUEUE}, fold+MD, count=${CELERY_GPU_COUNT}) ==="
  for (( gpu=0; gpu<CELERY_GPU_COUNT; gpu++ )); do
    pid_file="$PID_DIR/celery-gpu${gpu}.pid"
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      echo "  GPU $gpu: already running (PID $(cat "$pid_file"))"
      continue
    fi
    CUDA_VISIBLE_DEVICES="$gpu" nohup "$PY" -m celery -A app.celery_app worker \
      --loglevel=info \
      --concurrency=1 \
      -Q "${CELERY_GPU_QUEUE}" \
      -n "gpu${gpu}@%h" \
      >> "$LOG_DIR/celery-gpu${gpu}.log" 2>&1 &
    echo $! > "$pid_file"
    echo "  GPU $gpu: started PID $(cat "$pid_file")"
  done
}

start_api() {
  if [[ -f "$PID_DIR/api.pid" ]] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
    echo "API already running (PID $(cat "$PID_DIR/api.pid"))"
    return
  fi
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    pkill -f "uvicorn app.main:app" || true
    sleep 1
  fi
  nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
    >> "$LOG_DIR/api.log" 2>&1 &
  echo $! > "$PID_DIR/api.pid"
  sleep 1
  echo "API started PID $(cat "$PID_DIR/api.pid")"
}

start_gpu_workers

echo "=== Start API (background) ==="
start_api

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "=========================================="
echo "  BoltzFold 已在后台运行（可关闭此终端）"
echo "  本机:     http://127.0.0.1:${PORT}/"
[[ -n "${LAN_IP:-}" ]] && echo "  局域网:   http://${LAN_IP}:${PORT}/"
echo "  访问地址: bash scripts/show_access_urls.sh"
echo "  防火墙:   bash scripts/open_firewall_port.sh"
echo "  用户管理: bash scripts/manage_users.sh list --pending  # 审批待开通账号"
echo "  GPU:      ${CELERY_GPU_COUNT} Worker · 统一队列 ${CELERY_GPU_QUEUE}（折叠+MD 占满各卡）"
echo "  日志:     $LOG_DIR/api.log  $LOG_DIR/celery-gpu*.log"
echo "  状态:     bash scripts/status_platform.sh"
echo "  停止:     bash scripts/stop_platform.sh"
echo "=========================================="
