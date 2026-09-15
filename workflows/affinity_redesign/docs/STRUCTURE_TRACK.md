# 结构轨（AntiFold / ESM-IF1）

对齐 AntiFold（oxpig）与 Shanker et al. Science 2024 的复合物 inverse folding 打分思路。

## 方法

1. 读取 `input/complex.pdb` + `prepare/candidates_filtered.csv`
2. 用 **AntiFold**（默认）或 **ESM-IF1**（`structure_track.engine: esm_if1`）对抗体(+抗原)结构做 inverse folding
3. 每个突变：`dll = logit(mut) − logit(wt)`（对 logits 等价于 logP 差）
4. `dll > 0` 视为结构轨通过；按 `dll` 排序写入 `top_per_chain.csv`；默认 `top_per_chain: 0` 保留全部通过项（不截断）；设为正整数则每链最多保留 N 条；`maxrep=0` 不限制同一位点条数

## 输出

```text
round1/structure/scores.csv
round1/structure/top_per_chain.csv
round1/structure/logits_raw.csv
round1/structure/result.json
round1/structure/structure_worker.log
round1/structure/antifold_raw/   # AntiFold 原始 CSV
```

## 运行

```bash
affinity-redesign init --campaign runs/lycov1404_7mmo__demo
affinity-redesign structure --campaign runs/lycov1404_7mmo__demo
# 或
affinity-redesign round1 --campaign runs/lycov1404_7mmo__demo --structure-only
```

## 环境与权重

- Python：`$ANTIFOLD_PYTHON`（默认 maxwell env）
- 仓库：`$ANTIFOLD_ROOT` = `/home/pengpai/data/Company_Project/AntiFold`
- 权重：`AntiFold/models/model.pt`（首次缺失时由 AntiFold 自动下载）
- ESM-IF1 权重：`$TORCH_HOME/hub/checkpoints/esm_if1_gvp4_t16_142M_UR50.pt`

## 链映射

`campaign.yaml` 的 `chains.heavy / light / antigen` 对应 PDB 链 ID。  
7MMO demo：`H` / `L` / `A`。

FASTA 位点与 PDB 残基通过**序列对齐**映射。  
Worker 会预处理 PDB：常见非标残基（如 N 端 `PCA`→`GLN`）并转成 `ATOM`，避免 biotite 报错。
