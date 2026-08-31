#!/usr/bin/env bash
# 下载 PLM 轨 ESM-1b + ESM-1v 权重
# esm1v .pt 仅在 Meta CDN，无 ModelScope/HF 镜像；用 aria2 多连接加速。
set -euo pipefail

TORCH_HOME="${TORCH_HOME:-/home/pengpai/data/cache/torch}"
CKPT="${TORCH_HOME}/hub/checkpoints"
BASE="https://dl.fbaipublicfiles.com/fair-esm/models"
PYTHON="${ESM_PYTHON:-/home/pengpai/data/envs/boltz2/bin/python}"
ARIA2_CONN="${ARIA2_CONN:-16}"

mkdir -p "$CKPT"
cd "$CKPT"

verify_pt() {
  local f="$1"
  "$PYTHON" -c "import torch; torch.load('${f}', map_location='cpu', weights_only=False); print('OK')"
}

download_one() {
  local fname="$1"
  local url="${BASE}/${fname}"
  local tmp="${fname}.downloading"

  if [[ -f "$fname" ]] && verify_pt "$fname" >/dev/null 2>&1; then
    echo "[skip] $fname"
    return 0
  fi
  rm -f "$fname" "$tmp" "${fname}.aria2"
  echo "[dl] $fname"
  aria2c -x "$ARIA2_CONN" -s "$ARIA2_CONN" -k 1M \
    --file-allocation=none --continue=false --max-tries=0 --retry-wait=3 \
    -o "$tmp" "$url"
  mv "$tmp" "$fname"
  verify_pt "$fname"
  ls -lh "$fname"
}

if [[ "${ESM1V_ONLY:-0}" != "1" ]]; then
  download_one "esm1b_t33_650M_UR50S.pt"
fi
for i in 1 2 3 4 5; do
  download_one "esm1v_t33_650M_UR90S_${i}.pt"
done
echo "ALL DONE"
