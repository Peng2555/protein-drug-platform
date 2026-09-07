#!/usr/bin/env bash
# 在集群登录节点 / sbatch 作业里 source，供 Rosetta CLI 使用
# 路径：~/boltz2_rosetta/software/rosetta_cluster_env.sh

source /usr/share/Modules/init/bash 2>/dev/null || true
module load rosetta/v3.14 2>/dev/null || true

export LD_LIBRARY_PATH=/share/app/rosetta/rosetta-3.14/source/build/external/release/linux/5.14/64/x86/gcc/11/default:${LD_LIBRARY_PATH:-}
export ROSETTA_BIN=/share/app/rosetta/rosetta-3.14/source/bin
export ROSETTA3=/share/app/rosetta/rosetta-3.14/source
export ROSETTA3_DB=/share/app/rosetta/rosetta-3.14/database

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
fi

# conda activate rosetta-eval   # 由 sbatch 脚本激活
