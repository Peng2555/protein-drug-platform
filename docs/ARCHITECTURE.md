# 平台架构

本文描述当前蛋白质-药物计算平台的代码边界、生产入口和任务数据流。

## 五层结构

| 层级 | 主要目录 | 职责 |
|------|----------|------|
| 平台层 | `app/`、`frontend/src/` | FastAPI API、认证、数据库模型、业务 Service、任务查询与 Vue 页面 |
| Worker 层 | `worker/`、`app/celery_app.py` | 从 Redis 队列领取任务，更新 PostgreSQL 状态，调用 Runner |
| Runner 层 | `scripts/*_runner.py` | 组织输入、调用模型或命令行工具、解析结果并写出标准产物 |
| 算法包层 | `affinity_redesign/`、`workflows/hydro_redesign/`、`workflows/cic_profile/`、`workflows/tnp_profile/` | 可复用的候选生成、评分和分析实现 |
| 外部依赖与运行产物层 | `external/`、本机 conda/工具环境、`run/` 及兼容输出目录 | RAS/TNP 对照代码、Boltz2/IgGM/GROMACS/Rosetta 等工具，以及不进入 git 的任务结果 |

层与层之间保持单向调用：平台层不直接实现计算算法，Worker 负责调度，Runner 负责适配具体工具，算法包负责可测试的领域逻辑。PostgreSQL 保存用户、任务和结果元数据；Redis 同时承担 Celery broker/result backend；结构、轨迹、日志和分析文件保存在文件系统。

## 主要业务模块

- 结构预测与批量 VHH：Boltz2、ESMFold2，包含置信度及界面指标。
- MD 验证：GROMACS 显式溶剂模拟。
- 亲和力成熟与合成筛选：IgGM 采样、候选汇总和测序表匹配。
- 小分子/RAS 三元复合物对接：RDKit、Vina/GNINA 及外部 RAS 流程。
- 序列与结构设计：ESM-2 可开发性、ProteinMPNN、Rosetta 评价。
- 亲和力改造：`affinity_redesign/` 中的 PLM、AntiFold、Boltz2/Rosetta 重打分。
- 多肽遮蔽：RFdiffusion 与 ProteinMPNN。
- 抗体分析：亲水性改造、CIC profile、TNP profile。

对应 API 路由位于 `app/routers/`，业务参数校验和任务创建主要位于 `app/*_service.py`，异步任务统一定义在 `worker/tasks.py`。

## 任务数据流

```text
浏览器 / API 客户端
  → FastAPI Router（鉴权、参数校验）
  → Service（创建输出目录和 PostgreSQL 任务记录）
  → Celery / Redis（投递到 GPU 队列）
  → worker/tasks.py（领取任务、更新 running/done/failed）
  → scripts/*_runner.py（调用算法包或外部工具）
  → 输出目录（结构、指标、日志、轨迹等）
  → PostgreSQL（状态与结果索引）
  → API / Vue（轮询、展示、下载）
```

结构预测和 MD 当前共用可配置的 GPU 队列，每个 GPU Worker 的并发数为 1。其他业务也通过 `worker/tasks.py` 进入相应 Runner；具体输出根目录由 `.env` 中的变量控制。

## 生产与 legacy 入口

生产入口是：

- API 应用：`app/main.py`（`app.main:app`）。
- 启动脚本：`scripts/start_platform.sh`，负责初始化数据库、启动 Celery GPU Worker 和 Uvicorn。
- 前端：优先由 `app/main.py` 挂载 `frontend/dist/`；`/legacy-app` 保留旧页面。

Legacy 入口仅用于兼容和排障：

- `app/server.py`：无 PostgreSQL/Celery 的单机折叠原型。
- `scripts/start_server.sh`：只启动上述原型。
- `web/`：旧版静态页面，不再作为新功能开发位置。

`frontend/dist/` 是由 `frontend/src/` 构建得到的部署产物，不是源码，也不进入 git。若该目录不存在，生产 API 会回退到 `web/`（存在时），但这不代表 `web/` 是生产前端。

## 输出目录

目标布局是将所有运行产物集中到 `run/`，根目录的 `outputs/`、`md_outputs/` 等路径作为兼容入口。当前部分环境中的 `hydro_redesign_outputs/`、`cic_profile_outputs/`、`tnp_profile_outputs/` 仍可能是根目录实目录，而非指向 `run/` 的链接；备份和迁移时必须同时检查。详细规则见 [REPOSITORY.md](REPOSITORY.md)。
