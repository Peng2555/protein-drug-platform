#!/usr/bin/env bash
# Print URLs for accessing BoltzFold from this machine, LAN, and (if configured) public network.
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

echo "=========================================="
echo "  BoltzFold 访问地址（端口 ${PORT}）"
echo "=========================================="
echo ""
echo "  本机:     http://127.0.0.1:${PORT}/"
echo ""

if command -v hostname >/dev/null 2>&1; then
  echo "  局域网（同事同一 WiFi / 内网可试这些地址）:"
  found=0
  while IFS= read -r ip; do
    [[ -z "$ip" ]] && continue
    [[ "$ip" == 127.* ]] && continue
    echo "            http://${ip}:${PORT}/"
    found=1
  done < <(hostname -I 2>/dev/null | tr ' ' '\n' | sort -u)
  if [[ "$found" -eq 0 ]]; then
    echo "            （未检测到局域网 IP）"
  fi
  echo ""
fi

if command -v ss >/dev/null 2>&1; then
  if ss -tln | grep -q ":${PORT} "; then
    bind="$(ss -tln | awk -v p=":${PORT}" '$4 ~ p {print $4; exit}')"
    echo "  监听:     ${bind}"
    if echo "$bind" | grep -q '127.0.0.1'; then
      echo "  ⚠ 仅监听本机。请重启平台: bash scripts/start_platform.sh（默认 0.0.0.0）"
    else
      echo "  ✓ 已监听所有网卡，局域网用户可直接访问上述 IP"
    fi
  else
    echo "  ⚠ 端口 ${PORT} 未在监听。请先运行: bash scripts/start_platform.sh"
  fi
  echo ""
fi

echo "  外网访问（需额外配置）:"
echo "    1. 路由器端口转发: 外网端口 → 本机 IP:${PORT}"
echo "    2. 或使用 VPN 连入内网后访问局域网地址"
echo "    3. 生产环境建议 Nginx + HTTPS 反向代理"
echo ""
echo "  开发模式（热更新，可选）:"
echo "    cd frontend && npm run dev"
echo "    本机 http://127.0.0.1:5173/  局域网 http://<本机IP>:5173/"
echo ""
echo "  防火墙:   bash scripts/open_firewall_port.sh   # 如需放行 ${PORT}"
echo "=========================================="
