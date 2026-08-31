# Boltz2 Web 集成做法

算法在 `antibody_redesign`。网站只加一层任务：建 Job、调 `run_workflow`、展示 `exports/`。

**先不要把 AF3Score 接进 Web。**

## 1. 安装

Boltz2 的 worker / API 环境：

```bash
/path/to/boltz2-web-venv/bin/pip install -e /home/pengpai/data/Company_Project/antibody_redesign
```

`.env` 可与 CLI 共用（`ESM_PYTHON`、`ANTIFOLD_*`、`BOLTZ2_PYTHON`、`PYROSETTA_PYTHON`）。

## 2. Engine

```python
AFFINITY_REDESIGN_ENGINE = "affinity_redesign"
```

一个 Job = 一次 `run_workflow`（一个 campaign）。

## 3. 建议新增文件（对齐现有 Rosetta eval）

| 文件 | 做什么 |
|------|--------|
| `app/affinity_redesign_service.py` | `create_job`：收 FASTA、可选 PDB、写 work_dir |
| `app/routers/affinity_redesign_jobs.py` | `POST /api/affinity-redesign-jobs`、`GET` 状态与产物 |
| `worker/tasks.py` | `run_affinity_redesign_job` |
| 前端一页表单 + 一页结果表 | 上传序列 / 可选结构，结果读 CSV |

`work_dir` 直接用 campaign 目录结构（与 `runs/{slug}__{id}/` 相同）。

## 4. API 入参（两条入口）

`POST /api/affinity-redesign-jobs`

```json
{
  "name": "lycov1404",
  "fasta": ">H\n...\n>L\n...\n>A\n...",
  "complex_pdb": null,
  "skip_round1": false
}
```

- **有 `complex_pdb`（或上传文件）**：入口 A，拷到 `input/complex.pdb`
- **没有结构**：入口 B，workflow 先 Boltz2 折 WT

Worker：

```python
from affinity_redesign.pipeline.workflow import bootstrap_campaign, run_workflow

# 把 job.work_dir 当成 campaign
# 或 bootstrap 后再 run_workflow(campaign_dir, on_stage=...)
result = run_workflow(campaign_dir, on_stage=on_stage)
job.results_json = {
    "ranked_csv": ".../exports/ranked_mutations.csv",
    "wetlab_csv": ".../exports/wetlab_candidates.csv",
    "summary": result.get("rescore"),
}
```

`on_stage` 写 `job.stage`，前端就能显示 `fold_wt_complex` / `round1` / `boltz2_3/59_H_I31T` / `rosetta`。

进度文件也可读 `campaign/workflow_status.json`。

## 5. 前端怎么做

1. **提交页**（可仿 `/rosetta/new` 或 Fold 表单）
   - 必填：H、抗原（IgG 再加 L），或整段 FASTA
   - 选填：复合物 PDB
   - 提交 `POST` 后跳转任务详情
2. **结果页**
   - 表格：`ranked_mutations.csv`（列：rank、decision、tier、label、ΔipTM、ddG、wetlab）
   - 下载：`wetlab_candidates.csv` + `structures/` zip
   - 可链到已有「结构评价」页看 Rosetta `report.html`

## 6. 队列与耗时

这是长任务（demo 约 59 突变：Boltz2 约 1–3 小时 + Rosetta 数小时）。必须走 **Celery**，不要在 FastAPI 进程里同步跑。

GPU：Boltz2 阶段与现有 fold worker **共用 GPU 队列**；Rosetta 只吃 CPU，可另开 concurrency。

## 7. 产物给前端的路径

Job `work_dir`：

```text
exports/ranked_mutations.csv
exports/wetlab_candidates.csv
exports/structures/WT.pdb
exports/summary.json
round1/merged/tier_A.csv
workflow_status.json
```

静态文件或现有 `GET /api/jobs/{id}/files/...` 即可，不必新协议。
