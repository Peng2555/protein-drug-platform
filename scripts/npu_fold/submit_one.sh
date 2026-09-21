#!/usr/bin/env bash
# 在网站这台机器上调用：把一个 yaml 送到 npu-3，远程跑 run_one.sh，再把结果拷回来。
# 与 /data01/pengpai/her2_vhh 完全分开。
# 用法：
#   bash scripts/npu_fold/submit_one.sh --job-id ID --yaml /path/to.yaml [--device auto|0-7] [--local-out DIR]
#   DRY_RUN=1 bash scripts/npu_fold/submit_one.sh ...   只测传文件和远程脚本，不跑折叠
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${NPU_SSH_HOST:-npu-3}"
REMOTE_ROOT="${BOLTZFOLD_PLATFORM_ROOT:-/data01/pengpai/boltzfold_platform}"
JOB_ID=""
YAML=""
DEVICE="auto"
LOCAL_OUT=""

usage() {
  echo "用法: $0 --job-id ID --yaml FILE [--device auto|0-7] [--local-out DIR]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-id) JOB_ID="${2:-}"; shift 2 ;;
    --yaml) YAML="${2:-}"; shift 2 ;;
    --device) DEVICE="${2:-}"; shift 2 ;;
    --local-out) LOCAL_OUT="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done
[[ -n "$JOB_ID" && -n "$YAML" ]] || usage
[[ -f "$YAML" ]] || { echo "本地找不到 yaml: $YAML" >&2; exit 1; }

if [[ -z "$LOCAL_OUT" ]]; then
  LOCAL_OUT="${ROOT}/run/npu_fold_stage/${JOB_ID}"
fi
mkdir -p "${LOCAL_OUT}"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 "${HOST}")
RSYNC_SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

echo "==> 同步远程脚本到 ${HOST}:${REMOTE_ROOT}/scripts"
"${SSH[@]}" "mkdir -p '${REMOTE_ROOT}/scripts' '${REMOTE_ROOT}/work' '${REMOTE_ROOT}/locks'"
rsync -az -e "${RSYNC_SSH}" \
  "${ROOT}/scripts/npu_fold/run_one.sh" \
  "${HOST}:${REMOTE_ROOT}/scripts/run_one.sh"
"${SSH[@]}" "chmod +x '${REMOTE_ROOT}/scripts/run_one.sh'"

echo "==> 上传输入 ${YAML} → work/${JOB_ID}/input/input.yaml"
"${SSH[@]}" "mkdir -p '${REMOTE_ROOT}/work/${JOB_ID}/input' '${REMOTE_ROOT}/work/${JOB_ID}/output'"
rsync -az -e "${RSYNC_SSH}" \
  "${YAML}" \
  "${HOST}:${REMOTE_ROOT}/work/${JOB_ID}/input/input.yaml"

echo "==> 远程执行 job=${JOB_ID} device=${DEVICE} DRY_RUN=${DRY_RUN:-0}"
set +e
"${SSH[@]}" "DRY_RUN='${DRY_RUN:-0}' \
  USE_MSA_SERVER='${USE_MSA_SERVER:-1}' \
  RECYCLING_STEPS='${RECYCLING_STEPS:-3}' \
  SAMPLING_STEPS='${SAMPLING_STEPS:-200}' \
  DIFFUSION_SAMPLES='${DIFFUSION_SAMPLES:-1}' \
  MAX_PARALLEL_SAMPLES='${MAX_PARALLEL_SAMPLES:-1}' \
  MAX_MSA_SEQS='${MAX_MSA_SEQS:-8192}' \
  SUBSAMPLE_MSA='${SUBSAMPLE_MSA:-0}' \
  bash '${REMOTE_ROOT}/scripts/run_one.sh' --job-id '${JOB_ID}' --device '${DEVICE}'"
rc=$?
set -e

echo "==> 回传 output / 日志 → ${LOCAL_OUT}"
rsync -az -e "${RSYNC_SSH}" \
  "${HOST}:${REMOTE_ROOT}/work/${JOB_ID}/" \
  "${LOCAL_OUT}/"

echo "远程退出码: ${rc}"
echo "本地目录: ${LOCAL_OUT}"
exit "${rc}"
