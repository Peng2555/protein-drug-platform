# 抗体改造项目：数据与溯源设计

本文记录阶段一的数据边界。第一版坚持使用明确的业务实体，不引入通用工作流或事件溯源框架。

## 数据主链

```text
靶点项目 antibody_projects
  └─ 候选抗体 antibody_candidates
      └─ 序列版本 antibody_versions（WT、M1、M2……）
          ├─ 链序列 antibody_version_chains
          ├─ 相对父版本的突变 antibody_version_mutations
          ├─ 样品批次 antibody_sample_batches
          │   └─ 实验 antibody_experiments
          │       └─ 测量值 antibody_experiment_measurements
          └─ 现有计算任务关联 antibody_project_job_links
```

项目成员、附件和审计记录分别由 `antibody_project_members`、
`antibody_project_artifacts`、`antibody_audit_events` 保存。

## 核心规则

1. 一个项目对应一个靶点，可以包含多个候选抗体。
2. 候选抗体固定属于 RM、RN 或 RL；该分类与 IgG/VHH 分子形式分开保存。
   新候选必须选择分类，升级前的候选允许补录一次，设置后不能修改。
3. 每个候选抗体有一个 `WT`，改造版本在该候选抗体内按 `M1、M2……` 编号；
   同时保存数字序号（WT=0、M1=1），不能依赖字符串排序。
4. 版本通过 `primary_parent_id` 追溯直接来源；不允许以自身为父版本。
5. IgG 保存 VH、VL，VHH 保存 VHH；可变区必填，全长序列可选。
6. 序列入库前统一大写、去空白，并保存 SHA-256。版本哈希由按角色排序的链快照计算。
7. 草稿可以修改；锁定版本的序列、链和突变只能读取。此规则由后续 Service/API 统一执行。
8. 实验指向准确版本，可选择具体样品批次；指标拆成独立测量值，便于跨版本比较。
9. Job 关联同时保存 `job_id` 和 `original_job_id`。原 Job 删除后，实时外键可以置空，
   但原始 ID、输入哈希、参数与结果快照仍然保留。
10. 附件正文放文件系统，数据库保存路径、大小和 SHA-256。
11. 项目、锁定版本和已被引用的数据使用归档/状态变化，不执行日常物理删除。

## 审计记录

`antibody_audit_events` 是追加式记录，包含：

- 项目与被操作实体；
- 操作者、动作和时间；
- 修改前 `before_json`；
- 修改后 `after_json`；
- 可选请求 ID，用于把一次 API 操作产生的多条记录串联起来。

后续业务 Service 必须在同一数据库事务中同时保存业务修改和审计记录。审计表不提供编辑接口。

## 文件布局

默认根目录由 `ANTIBODY_PROJECTS_OUT_ROOT` 配置：

```text
run/antibody_projects/
  └─ <project-uuid>/
      ├─ versions/
      ├─ experiments/
      ├─ jobs/
      └─ reports/
```

上传时必须计算 SHA-256；下载或备份恢复后可以再次计算并核对。数据库中保存相对业务含义，
文件系统负责保存大文件本体。

## 数据库迁移

Alembic 迁移链：

- `0001_legacy_schema`：为原有 `users/batches/jobs` 建立无损基线。表已存在时不重建。
- `0002_antibody_projects`：新增抗体项目领域表，不修改原任务数据。

生产升级前先备份数据库和运行目录，再执行：

```bash
python -m alembic upgrade head
python -m alembic current
```

平台启动脚本会通过 `scripts/init_db.py` 自动执行相同升级。生产数据库降级可能删除新模块数据，
只能在完整备份后进行。

## 阶段二 API

API 统一使用 `/api/antibody-projects` 前缀，主要资源包括：

- 项目及成员：项目创建、查询、状态修改，以及 owner/editor/viewer 权限；
- 候选抗体：创建候选时同时创建并锁定 WT；
- 序列版本：自动生成 M1、M2，自动计算突变，草稿编辑和版本锁定；
- 对比：按两份完整序列快照即时计算替换、插入和删除；
- 样品与实验：锁定版本才能创建样品和实验，首次实验会把版本标记为 tested；
- 任务关联：保存 Job 输入哈希、参数和结果快照；
- 附件：文件系统保存正文，数据库保存 SHA-256 和关联对象；
- 审计：业务修改与 before/after 快照在同一事务写入。

项目成员只有负责人可以调整；editor 可以修改研发数据；viewer 只能查看和下载。无项目权限时
统一返回 404，避免泄露项目是否存在。

## 阶段三 Web 工作台

前端入口为 `/antibody-projects`，项目详情使用标签页组织：

- 版本管理：候选抗体、WT、M1/M2、链序列、突变说明与锁定；
- 序列对比：同一候选抗体的两个版本及差异位点；
- 样品与实验：样品批次、五类实验和多个测量指标；
- 任务与文件：关联已有 Job、上传与下载附件；
- 项目概览：项目阶段和成员；
- 操作历史：查看不可编辑的审计快照。

页面按资源拆分为小组件，数据访问集中在 `frontend/src/api/antibodyProjects.ts`，
没有新增全局状态或前端工作流框架。
