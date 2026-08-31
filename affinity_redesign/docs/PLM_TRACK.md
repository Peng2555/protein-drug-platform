# 序列 PLM 轨

对齐 Hie et al., *Nat Biotechnol* 2023。

## 方法

1. 读取 `prepare/candidates_filtered.csv`
2. 用 **ESM-1b + ESM-1v×5** 对每条 binder 链做 wild-type marginal 打分
3. 每个突变：`dll = logP(mut) − logP(wt)`
4. **共识**：至少 `consensus_k`（默认 3）个模型满足 `dll > 0`
5. 按 `mean_dll` 排序写入 `top_per_chain.csv`；默认 `top_per_chain: 0` 保留全部共识通过（不截断）；设为正整数则每链最多保留 N 条；`maxrep=0` 不限制同一位点条数

## 输出

```text
round1/plm/scores.csv
round1/plm/top_per_chain.csv
round1/plm/result.json
round1/plm/plm_worker.log
```

## 运行

```bash
affinity-redesign init --campaign runs/lycov1404_7mmo__demo
affinity-redesign plm --campaign runs/lycov1404_7mmo__demo
# 或
affinity-redesign round1 --campaign runs/lycov1404_7mmo__demo --plm-only
```

## 权重

放在 `$TORCH_HOME/hub/checkpoints/`（默认 `/home/pengpai/data/cache/torch/hub/checkpoints`）：

- `esm1b_t33_650M_UR50S.pt`
- `esm1v_t33_650M_UR90S_{1..5}.pt`
