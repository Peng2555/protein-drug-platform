# 本机侧：Rosetta 迁集群（已完成项）

Web / Boltz2 / Celery **仍在本机**。本机已准备好「可开关的集群投递」，默认**关闭**，不影响现网。

## 已完成

1. SSH：`cluster-cpu` → `bj3212@172.16.6.1`（密钥登录）
2. 桥接脚本：`scripts/rosetta_cluster_bridge.py`（rsync → sbatch → 轮询 → rsync 回）
3. 本机一键准备：`bash scripts/rosetta_cluster_setup_local.sh`
4. 流水线接入：`affinity_redesign/.../rescore.py` 的 `_run_rosetta`
5. `.env` 配置项（`ROSETTA_CLUSTER_ENABLED=false`）

## 试跑 inputs 路径

```
/home/pengpai/data/Company_Project/Boltz2/affinity_redesign_outputs/21A060-B36F12亲和力改造__d751aa5d/round1/rescore/rosetta/inputs/
```

共 72 个 PDB（含 WT）。

## 打开自动投递（集群环境就绪后）

1. 集群完成：`conda create -n rosetta-eval python=3.11 gemmi` + Rosetta module
2. 本机 `.env`：`ROSETTA_CLUSTER_ENABLED=true`
3. **重启 Celery GPU worker**（读新环境变量；API 可不动）
4. 新亲和力改造任务到 Rosetta 阶段会走集群；失败且 `FALLBACK_LOCAL=true` 时回退本机

## 本机手工试跑 bridge

```bash
bash scripts/rosetta_cluster_setup_local.sh   # 若尚未同步

export ROSETTA_CLUSTER_HOST=cluster-cpu
export ROSETTA_CLUSTER_WORKDIR=/share/home/bj3212/boltz2_rosetta
DEMO=/home/pengpai/data/Company_Project/Boltz2/affinity_redesign_outputs/21A060-B36F12亲和力改造__d751aa5d/round1/rescore/rosetta

/home/pengpai/data/envs/boltz2/bin/python scripts/rosetta_cluster_bridge.py \
  --local-work-dir "$DEMO" \
  --job-name demo001 \
  --wt "$DEMO/inputs/WT.pdb" \
  --antibody-chains H --antigen-chains A \
  --n-jobs 64 --nstruct 1
```

成功后本地 `$DEMO/scores.csv` 会被集群结果覆盖（注意：会改已有试跑目录，正式联调可换新 work-dir）。
