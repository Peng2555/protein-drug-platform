#!/usr/bin/env bash
# Try to open BoltzFold port for LAN access (requires sudo for ufw).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8765}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PORT="${PORT:-8765}"

echo "=== 放行 BoltzFold 端口 ${PORT}（局域网访问）==="

if command -v ufw >/dev/null 2>&1; then
  status="$(sudo ufw status 2>/dev/null || true)"
  if [[ -z "$status" ]]; then
    echo "无法读取 ufw 状态（可能需要 sudo 密码）"
    exit 1
  fi
  if echo "$status" | grep -qi inactive; then
    echo "ufw 未启用。若仍无法访问，请检查 iptables 或云厂商安全组。"
    exit 0
  fi
  if echo "$status" | grep -q "${PORT}/tcp"; then
    echo "端口 ${PORT}/tcp 已在 ufw 规则中。"
  else
    echo "添加规则: ufw allow ${PORT}/tcp"
    sudo ufw allow "${PORT}/tcp" comment 'BoltzFold platform'
    echo "已添加。当前状态:"
    sudo ufw status | grep -E "${PORT}|Status" || true
  fi
else
  echo "未检测到 ufw。若使用 firewalld，可手动执行:"
  echo "  sudo firewall-cmd --add-port=${PORT}/tcp --permanent && sudo firewall-cmd --reload"
  echo "云服务器还需在控制台「安全组」中放行 TCP ${PORT}。"
fi

echo ""
bash "$(dirname "$0")/show_access_urls.sh"
