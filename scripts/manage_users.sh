#!/usr/bin/env bash
# Run user management with the same Python env as the BoltzFold platform.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/pengpai/data/envs/boltz2/bin/python}"

if [[ ! -x "$PY" ]]; then
  echo "错误: 未找到 Python 环境: $PY" >&2
  echo "请设置 PY=你的conda/python路径，例如:" >&2
  echo "  PY=/path/to/boltz2/bin/python bash scripts/manage_users.sh list" >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/manage_users.py" "$@"
