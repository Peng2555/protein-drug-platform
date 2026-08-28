#!/usr/bin/env bash
# 在 /data 安装 PyRosetta 季度版（与 Rosetta ref2015 同一能量函数）。
# 官方完整 Linux 二进制约 18GB 且需单独许可证；PyRosetta wheel 约 1.6GB，适合本机系统盘已满的情况。
set -euo pipefail
PREFIX="${PYROSETTA_PREFIX:-/home/pengpai/data/envs/pyrosetta}"
WHEEL="${PYROSETTA_WHEEL:-https://west.rosettacommons.org/pyrosetta/quarterly/release/pyrosetta-0-cp311-cp311-linux_x86_64.whl}"
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-/home/pengpai/data/cache/conda-pkgs}"
export TMPDIR="${TMPDIR:-/home/pengpai/data/cache/tmp}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/home/pengpai/data/cache/pip}"
mkdir -p "$CONDA_PKGS_DIRS" "$TMPDIR" "$PIP_CACHE_DIR"

if [[ ! -x "$PREFIX/bin/python" ]]; then
  /home/pengpai/miniconda3/bin/conda create -p "$PREFIX" python=3.11 pip numpy -y
fi

"$PREFIX/bin/python" -m pip install --upgrade pip
"$PREFIX/bin/python" -m pip install "$WHEEL" gemmi
"$PREFIX/bin/python" - <<'PY'
import pyrosetta
pyrosetta.init("-mute all -ignore_unrecognized_res")
print("PyRosetta OK", pyrosetta.version())
PY
echo "Installed: $PREFIX/bin/python"
