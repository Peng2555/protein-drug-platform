# 平台架构

本文是当前代码的地图：层、业务模块、队列、产物目录，以及生产和 legacy 入口。模块行为以代码为准；抗体项目的表和不可变规则见 [`ANTIBODY_PROJECTS_DATA.md`](ANTIBODY_PROJECTS_DATA.md)。

## 代码分层

层与层之间单向调用：页面和 API 不实现算法，Worker 只调度，Runner 适配外部工具，算法包放可测试的领域逻辑。

| 层级 | 主要目录 | 职责 |
|------|----------|------|
| 平台层 | `app/`、`frontend/src/` | FastAPI、认证、数据库模型、业务 Service、Vue 页面 |
| Worker 层 | `worker/`、`app/core/celery.py`、`app/core/queue.py` | 从 Redis 领任务，更新任务状态，调用 Runner |
| Runner 层 | `scripts/*_runner.py` 及合成筛选脚本 | 组织输入、调用模型或命令行、写出标准产物 |
| 算法包层 | `workflows/` | 亲和力改造、疏水改造、CIC、TNP、额外二硫键 |
| 共享库 | `shared/src/boltzfold_shared/` | 序列/结构 IO、抗体 CDR、SASA、Boltz2 worker 辅助 |
| Boltz2 适配 | `integrations/boltz2/` | 输入、进程、结果解析，以及昇腾 NPU 远程折叠 |
| 外部依赖与产物 | `external/`、本机 conda/工具、`run/` | RAS 子模块、TNP 本地副本、不进 git 的任务结果 |

`algorithm_paths.py` 把 `shared/src` 和五个 `workflows/*/src` 放进 `sys.path`，部署时可以不先做 editable install。

PostgreSQL 保存用户、任务和结果元数据；Redis 同时做 Celery broker 和 result backend。结构、轨迹、日志和分析文件在文件系统。Pydantic schema 在 `app/schemas/`，跨模块辅助在 `app/common/`。路由注册表是 `app/modules/__init__.py` 的 `ROUTERS`，由 `app/main.py` 一次挂上。

## 业务模块

每个计算模块在 `app/modules/<name>/` 里放 Router 和 Service。前端计算页大多是同一套四段路由：工作台、新建、任务列表、任务详情。`/jobs/:id` 会重定向到 `/task/:id`。

| 模块 | 页面 | API 前缀 | Worker 任务 | 默认队列 | Runner / 算法 | 产物配置 |
|------|------|----------|-------------|----------|---------------|----------|
| 结构预测 | `/fold` | `/api/jobs`、`/api/batches` | `run_fold_job` | 见下方队列 | `boltz_runner`、`esmfold_runner`，以及 `pdockq_runner`、`dockq_runner` | `BOLTZ2_OUT_ROOT` → `outputs/` |
| MD 验证 | `/md` | `/api/md-jobs` | `run_md_job` | `gpu` | `md_runner`（GROMACS） | `md_outputs/` |
| 亲和力成熟 | `/maturation` | `/api/maturation-jobs` | `run_maturation_job` | `gpu` | `iggm_maturation_runner` | `maturation_outputs/` |
| 合成筛选 | `/synthesis` | `/api/synthesis-jobs` | 无。请求内同步完成 | — | `iggm_shm_matcher`、`iggm_synthesis_order` | `synthesis_outputs/` |
| 小分子对接 | `/docking` | `/api/docking-jobs` | `run_small_molecule_docking_job` | `gpu` | `docking_runner`（Vina） | `docking_outputs/` |
| RAS 对接 | 前端 `/ras-docking` 转到 `/docking` | `/api/ras-docking-jobs` | `run_ras_docking_job` | `gpu` | `ras_docking_runner` + `external/ras-tricomplex-docking` | `docking_outputs/` |
| 序列改造 | `/developability` | `/api/developability-jobs` | `run_developability_job` | `gpu` | `esm2_developability_runner` | `developability_outputs/` |
| 序列设计 | `/design` | `/api/design-jobs` | `run_design_job` | `gpu` | `proteinmpnn_design_runner` | `design_outputs/` |
| Rosetta 评价 | `/rosetta` | `/api/rosetta-eval-jobs` | `run_rosetta_eval_job` | `gpu` | `rosetta_eval_runner` | `rosetta_eval_outputs/` |
| 亲和力改造 | `/affinity-redesign` | `/api/affinity-redesign-jobs` | `run_affinity_redesign_job` | `gpu` | `affinity_redesign_runner` → `workflows/affinity_redesign/` | `affinity_redesign_outputs/` |
| 多肽遮蔽 | `/masking-peptide` | `/api/masking-peptide-jobs` | `run_masking_peptide_job` | `gpu` | `masking_peptide_runner`（RFdiffusion、ProteinMPNN） | `masking_peptide_outputs/` |
| 疏水性改造 | `/hydro-redesign` | `/api/hydro-redesign-jobs` | `run_hydro_redesign_job` | 折叠计算队列 | `hydro_redesign_runner` → `workflows/hydro_redesign/` | `run/hydro_redesign_outputs/` |
| CIC 表面斑 | `/cic-profile` | `/api/cic-profile-jobs` | `run_cic_profile_job` | 折叠计算队列 | `cic_profile_runner` → `workflows/cic_profile/` | `run/cic_profile_outputs/` |
| VHH 可开发性画像 | `/tnp-profile` | `/api/tnp-profile-jobs` | `run_tnp_profile_job` | `gpu` | `tnp_profile_runner` → `workflows/tnp_profile/` | `run/tnp_profile_outputs/` |
| 额外二硫键 | `/tm-disulfide` | `/api/tm-disulfide-jobs` | `run_tm_disulfide_job` | `cpu` | `tm_disulfide_runner` → `workflows/tm_disulfide/` | `run/tm_disulfide_outputs/` |
| 抗体改造项目 | `/antibody-projects` | `/api/antibody-projects` | 无。关联已有 `jobs` | — | — | `run/antibody_projects/` |
| 账号 | `/login`、`/admin/users` | `/api/auth` | 无 | — | — | — |

页面上还有首页 `/home`、工具目录 `/app`、场景 `/use-cases/:id`、流水线说明 `/workflows`，以及旧界面 iframe `/legacy`。这些页面不单独创建计算任务。

疏水改造和 TNP 画像另有批量详情页：`/hydro-redesign/batch/:id`、`/tnp-profile/batch/:id`。结构预测批次是 `/fold/batches/:id`。

## 队列

`scripts/start_platform.sh` 拉起三类 Worker。任务实际进哪个队列，看 Service 调用的 `app/core/queue.py`，不看 Celery `task_routes` 里的少数默认项。

| 队列 | 环境变量 | Worker | 谁会进来 |
|------|----------|--------|----------|
| `gpu` | `CELERY_GPU_QUEUE`，每卡一个进程，并发 1 | 本机 NVIDIA | 默认队列。MD、ESMFold、成熟、设计、可开发性、Rosetta、亲和力改造、遮蔽肽、两种对接、TNP |
| `fold` | `CELERY_FOLD_QUEUE`，仅 `BOLTZ_NPU_REMOTE=1` 时启动 | 本机不占 GPU，转远程 NPU | Boltz2 结构预测；疏水改造和 CIC 在远程开关打开时也走这里 |
| `cpu` | `CELERY_CPU_QUEUE` | 不占 GPU | 额外二硫键（PyRosetta） |

结构预测的分流在 `app/modules/fold/service.py`：`engine` 为 ESMFold2 时始终进 `gpu`；Boltz2 在 `BOLTZ_NPU_REMOTE` 打开时进 `fold`，否则进 `gpu`。疏水和 CIC 用 `dispatch_fold_compute`：远程开关打开进 `fold`，否则进 `gpu`。TNP 固定进 `gpu`。合成筛选在 API 进程里算完，不进队列。

健康检查 `/api/health` 会把这三条队列的长度加在一起。

## 任务数据流

```text
浏览器 / API 客户端
  → FastAPI Router（鉴权、参数校验）
  → Service（创建输出目录和 PostgreSQL 任务记录）
  → Celery / Redis（gpu、fold 或 cpu）
  → worker/tasks/（更新 running / done / failed）
  → scripts/*_runner.py（调用 workflows/、integrations/boltz2 或外部工具）
  → run/ 下的输出目录（结构、指标、日志、轨迹）
  → PostgreSQL（状态与结果索引）
  → API / Vue（轮询、展示、下载）
```

合成筛选停在 Service，直接调用 `scripts/` 里的匹配和排序脚本。抗体项目不产生自己的计算任务，用 `antibody_project_job_links` 指向已有 `jobs`。

## 生产与 legacy 入口

生产入口：

- API：`app/main.py`（`app.main:app`），默认端口 `8765`。
- 启停：`scripts/start_platform.sh`、`scripts/status_platform.sh`、`scripts/stop_platform.sh`。启动时做数据库迁移，并拉起 GPU Worker；远程折叠和 CPU Worker 按配置启动。
- 前端：存在 `frontend/dist/` 时挂到 `/`。未知路径回退 `index.html`，但 `/api/` 仍返回 404。

Legacy 只用于兼容和排障：

- `app/legacy/server.py`：无 PostgreSQL / Celery 的单机折叠原型。
- `scripts/start_server.sh`：只启动上述原型。
- `web/`：旧静态页，挂在 `/legacy-app`。Vue 里的 `/legacy` 用 iframe 打开它。

`frontend/dist/` 由 `frontend/src/` 构建，不进 git。目录不存在时，API 会回退挂载 `web/`（若存在）。回退不表示 `web/` 是生产前端。

## 输出目录

任务文件的实际位置是 `run/`。根目录的 `outputs/`、`md_outputs/`、`logs/` 等是指向 `run/` 对应子目录的符号链接，给 `.env` 和历史 `work_dir` 用。

配置默认值有两种写法，解析后都在 `run/` 里：

- 较早的模块写成仓库根下的名字，例如 `outputs/`、`md_outputs/`。这些名字现在是链接。
- 疏水、CIC、TNP、额外二硫键和抗体项目直接写成 `run/<name>/`。

`run/` 里还有 `npu_fold_stage/`，给远程折叠暂存用，没有对应的根目录链接。小分子对接和 RAS 对接共用 `docking_outputs/`。

备份时复制 `run/` 即可覆盖当前这些产物。若某台旧机器上的同名路径仍是实目录而不是链接，要单独纳入备份。链接本身可以重建。规则见 [REPOSITORY.md](REPOSITORY.md) 和 [BACKUP.md](BACKUP.md)。
