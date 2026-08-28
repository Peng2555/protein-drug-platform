# Rosetta 抗体–抗原结构评价

SOP：Boltz2/ESMFold 复合物 PDB/CIF → 去溶剂标准化 → **约束 FastRelax** → 选最低能量模型 → InterfaceAnalyzer → 相对 WT 的 ΔΔG / ΔE → 多指标排序。

相对原始 GPT 草案的修正：

1. **链 ID 自动识别**：本平台纳米抗体常见 `H`（VHH）+ `A`（抗原），不是固定 `A_B`。未指定时按 `H/A`、`H+L/A`、链长启发式识别。
2. **约束 Relax**：对预测复合物使用 `-relax:constrain_relax_to_start_coords`，避免把界面漂走。
3. **InterfaceAnalyzer**：使用 `-pack_separated true` 与 `-compute_packstat true`，`dG_separated` 才有可比性。
4. **nstruct 默认 3**（可 1–10）。100 个突变 × nstruct=5 的 CPU 代价很大。
5. **并行 `n_jobs`（默认 16，环境变量 `ROSETTA_N_JOBS`）**：PyRosetta 按「变体 × nstruct」拆成多进程（spawn）；单次 FastRelax 仍基本单线程。
6. **ESM2_LLR / 可开发性**为可选列；缺失时自动把权重归一到现有指标。
7. **计算后端优先 PyRosetta 季度版**（与 Rosetta 同一套 ref2015）。完整 Linux 二进制约 18GB 且需单独许可证，本机系统盘已满，因此装在 `/data`。若存在 `relax`/`InterfaceAnalyzer` 命令行，仍可走 CLI。

## 环境

安装（一次性）：

```bash
bash scripts/install_pyrosetta.sh
```

在 `.env` 中设置：

```
PYROSETTA_PYTHON=/home/pengpai/data/envs/pyrosetta/bin/python
ROSETTA_N_JOBS=16
```

可选：若另有 Rosetta 3.14 命令行，再设 `ROSETTA_BIN_DIR`。

依赖：Python 3.11、PyRosetta 2026.29 quarterly、gemmi。

## CLI（可复现、不经 Web）

请用 PyRosetta 解释器：

```bash
/home/pengpai/data/envs/pyrosetta/bin/python scripts/rosetta_eval_runner.py \
  --work-dir /tmp/rosetta_eval_demo \
  --wt WT.pdb \
  --mutant mutant_001.pdb mutant_002.pdb \
  --nstruct 3 \
  --n-jobs 16
```

输出：

- `scores.csv` / `ranking.csv`
- `report.html`
- `summary.json`
- `relaxed_structures/*_relax.pdb`
- `variants/<name>/relax/` 与 `interface/`（flags、log、scorefile）

## 平台模块

导航：**序列与抗体 → 结构评价**（`/rosetta/new`）。

- 来源：已完成折叠任务（指定 WT + 多个突变体）或上传 PDB/CIF
- 从结构预测详情页可「启动结构评价」，会预填 WT
- 任务引擎名：`rosetta_interface_eval`

## 排序

默认权重：界面能 0.35 + 稳定性 0.20 + Boltz2 置信度 0.20 + ESM2_LLR 0.15 + 可开发性 0.10。缺项权重归零并归一。`final_score` 越大越好。

质控标记：`severe_clash`、`unstable_interface`（dSASA 相对 WT 下降 >50%）、`lost_hbonds`。
