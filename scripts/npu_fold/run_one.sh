#!/usr/bin/env bash
# 昇腾单任务折叠（与 her2_vhh 分片脚本分开，不写死 HER2 路径）。
# 在 npu-3 上执行：一张卡、一个 yaml。
# 用法：
#   run_one.sh --job-id JOB [--device 0-7|auto]
#   DRY_RUN=1 run_one.sh ...   只打印命令，不跑 boltz
set -euo pipefail

ENV_SH="${BOLTZ_ENV_SH:-/data01/pengpai/env.sh}"
ROOT="${BOLTZFOLD_PLATFORM_ROOT:-/data01/pengpai/boltzfold_platform}"
JOB_ID=""
DEVICE="${ASCEND_RT_VISIBLE_DEVICES:-auto}"

USE_MSA_SERVER="${USE_MSA_SERVER:-1}"
RECYCLING_STEPS="${RECYCLING_STEPS:-3}"
SAMPLING_STEPS="${SAMPLING_STEPS:-200}"
DIFFUSION_SAMPLES="${DIFFUSION_SAMPLES:-1}"
MAX_PARALLEL_SAMPLES="${MAX_PARALLEL_SAMPLES:-1}"
MAX_MSA_SEQS="${MAX_MSA_SEQS:-8192}"
SUBSAMPLE_MSA="${SUBSAMPLE_MSA:-0}"
NUM_SUBSAMPLED_MSA="${NUM_SUBSAMPLED_MSA:-1024}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-mmcif}"
OVERRIDE="${OVERRIDE:-1}"
NO_KERNELS="${NO_KERNELS:-1}"

usage() {
  echo "用法: $0 --job-id ID [--device 0-7|auto]" >&2
  echo "输入必须已在: ${ROOT}/work/<ID>/input/input.yaml" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-id) JOB_ID="${2:-}"; shift 2 ;;
    --device) DEVICE="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done
[[ -n "$JOB_ID" ]] || usage

# CANN set_env.sh 会读未定义的 LD_LIBRARY_PATH；临时关掉 nounset
set +u
# shellcheck disable=SC1091
source "${ENV_SH}"
set -u
export BOLTZ_CACHE="${BOLTZ_CACHE:-/data01/pengpai/weights}"
export CPU_AFFINITY_CONF="${CPU_AFFINITY_CONF:-1}"
export TASK_QUEUE_ENABLE="${TASK_QUEUE_ENABLE:-2}"
export PYTHONUNBUFFERED=1
export PYTORCH_NPU_ALLOC_CONF="${PYTORCH_NPU_ALLOC_CONF:-expandable_segments:True}"

JOB_DIR="${ROOT}/work/${JOB_ID}"
IN_YAML="${JOB_DIR}/input/input.yaml"
OUT_DIR="${JOB_DIR}/output"
LOG="${JOB_DIR}/log.txt"
LOCK_ROOT="${ROOT}/locks"
LOCK_DIR=""

mkdir -p "${OUT_DIR}" "${LOCK_ROOT}" "$(dirname "${LOG}")"

if [[ ! -f "${IN_YAML}" ]]; then
  echo "找不到输入: ${IN_YAML}" >&2
  exit 1
fi

release_lock() {
  if [[ -n "${LOCK_DIR}" && -d "${LOCK_DIR}" ]]; then
    rmdir "${LOCK_DIR}" 2>/dev/null || true
  fi
}
trap release_lock EXIT

acquire_device() {
  local want="$1"
  local d
  if [[ "${want}" == "auto" || -z "${want}" ]]; then
    for d in 0 1 2 3 4 5 6 7; do
      if mkdir "${LOCK_ROOT}/npu${d}" 2>/dev/null; then
        LOCK_DIR="${LOCK_ROOT}/npu${d}"
        DEVICE="${d}"
        return 0
      fi
    done
    echo "8 张 NPU 都在忙，请稍后重试" >&2
    return 1
  fi
  if ! mkdir "${LOCK_ROOT}/npu${want}" 2>/dev/null; then
    echo "NPU ${want} 已被占用" >&2
    return 1
  fi
  LOCK_DIR="${LOCK_ROOT}/npu${want}"
  DEVICE="${want}"
}

acquire_device "${DEVICE}" || exit 75

export ASCEND_RT_VISIBLE_DEVICES="${DEVICE}"

CMD=(
  boltz predict "${IN_YAML}"
  --cache "${BOLTZ_CACHE}"
  --out_dir "${OUT_DIR}"
  --accelerator npu
  --devices 1
  --num_workers 0
  --model boltz2
  --recycling_steps "${RECYCLING_STEPS}"
  --sampling_steps "${SAMPLING_STEPS}"
  --diffusion_samples "${DIFFUSION_SAMPLES}"
  --max_parallel_samples "${MAX_PARALLEL_SAMPLES}"
  --max_msa_seqs "${MAX_MSA_SEQS}"
  --num_subsampled_msa "${NUM_SUBSAMPLED_MSA}"
  --output_format "${OUTPUT_FORMAT}"
)
if [[ "${NO_KERNELS}" == "1" ]]; then
  CMD+=(--no_kernels)
fi
if [[ "${USE_MSA_SERVER}" == "1" ]]; then
  CMD+=(--use_msa_server --msa_pairing_strategy greedy)
fi
if [[ "${SUBSAMPLE_MSA}" == "1" ]]; then
  CMD+=(--subsample_msa)
fi
if [[ "${OVERRIDE}" == "1" ]]; then
  CMD+=(--override)
fi

{
  echo "=== START job=${JOB_ID} device=${DEVICE} $(date -Iseconds) ==="
  echo "yaml=${IN_YAML}"
  echo "out=${OUT_DIR}"
  printf 'cmd:'
  printf ' %q' "${CMD[@]}"
  echo
} | tee "${LOG}"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN=1，不调用 boltz" | tee -a "${LOG}"
  echo "${DEVICE}" > "${JOB_DIR}/device.txt"
  exit 0
fi

set +e
"${CMD[@]}" >>"${LOG}" 2>&1
rc=$?
set -e
echo "=== END job=${JOB_ID} rc=${rc} $(date -Iseconds) ===" | tee -a "${LOG}"
echo "${DEVICE}" > "${JOB_DIR}/device.txt"
echo "${rc}" > "${JOB_DIR}/exit_code.txt"
exit "${rc}"
