#!/usr/bin/env bash
# 本机侧：准备集群工作目录 + 同步 runner +（可选）推送试跑 inputs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${ROSETTA_CLUSTER_HOST:-cluster-cpu}"
REMOTE_ROOT="${ROSETTA_CLUSTER_WORKDIR:-/share/home/bj3212/boltz2_rosetta}"
DEMO_LOCAL="${1:-$ROOT/affinity_redesign_outputs/21A060-B36F12亲和力改造__d751aa5d/round1/rescore/rosetta}"

echo "=== 1. SSH ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" 'echo OK; whoami; hostname; echo HOME=$HOME'

echo "=== 2. 远程目录 ==="
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE_ROOT'/{software,jobs,logs} && ls -ld '$REMOTE_ROOT'"

echo "=== 3. 同步 rosetta_eval_runner.py + bridge 说明 ==="
rsync -a "$ROOT/scripts/rosetta_eval_runner.py" "$HOST:$REMOTE_ROOT/software/"
rsync -a "$ROOT/scripts/rosetta_cluster_env.sh" "$HOST:$REMOTE_ROOT/software/" 2>/dev/null || true

echo "=== 4. 推送试跑 inputs（demo001）==="
if [[ -d "$DEMO_LOCAL/inputs" ]]; then
  ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE_ROOT/jobs/demo001/inputs' '$REMOTE_ROOT/jobs/demo001/logs'"
  rsync -a "$DEMO_LOCAL/inputs/" "$HOST:$REMOTE_ROOT/jobs/demo001/inputs/"
  echo "demo inputs: $(ssh -o BatchMode=yes "$HOST" "ls '$REMOTE_ROOT/jobs/demo001/inputs'/*.pdb | wc -l") pdb files"
else
  echo "WARN: 找不到试跑目录 $DEMO_LOCAL/inputs ，跳过 demo 推送"
fi

cat <<EOF

本机准备完成。

集群工作目录: $HOST:$REMOTE_ROOT
试跑 inputs:   $HOST:$REMOTE_ROOT/jobs/demo001/inputs/  （若已推送）

下一步请在【集群】完成：
  1) conda create -n rosetta-eval python=3.11 gemmi -c conda-forge
  2) module load rosetta/v3.14 + LD_LIBRARY_PATH
  3) 用 sbatch 跑通 demo（或本机执行 bridge 试跑）

本机试跑 bridge（集群环境就绪后）:
  export ROSETTA_CLUSTER_HOST=$HOST
  export ROSETTA_CLUSTER_WORKDIR=$REMOTE_ROOT
  /home/pengpai/data/envs/boltz2/bin/python $ROOT/scripts/rosetta_cluster_bridge.py \\
    --local-work-dir "$DEMO_LOCAL" \\
    --job-name demo001 \\
    --wt "$DEMO_LOCAL/inputs/WT.pdb" \\
    --antibody-chains H --antigen-chains A \\
    --n-jobs 64 --nstruct 1

Web 自动投递：在 .env 设 ROSETTA_CLUSTER_ENABLED=true 后重启 Celery（API 可不动）。
EOF
