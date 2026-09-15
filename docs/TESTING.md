# 测试与验收

测试分为 Python 单元测试、前端类型检查与构建，以及连接真实基础设施和外部工具的 smoke test。运行命令前先进入项目根目录并激活对应环境。

## Python 测试

平台当前的 pytest 测试位于 `tests/`：

```bash
PYTHONPATH=. python -m pytest -q tests
```

亲和力改造算法包有独立测试：

```bash
PYTHONPATH=affinity_redesign/src python -m pytest -q affinity_redesign/tests
```

若环境尚未安装 pytest，可在开发环境中安装；pytest 不是平台运行时服务的必要依赖。部分测试会根据本机条件跳过或需要额外算法依赖，不应为了让最小平台环境通过测试而强行混装所有模型环境。

## 前端构建

前端当前没有独立的浏览器测试套件，`npm run build` 同时执行 `vue-tsc -b` 类型检查和 Vite 生产构建：

```bash
cd frontend
npm ci
npm run build
```

也可从根目录运行：

```bash
bash scripts/build_frontend.sh
```

成功标准是命令退出码为 0，且生成 `frontend/dist/index.html`。`frontend/dist/` 是可重建产物，不提交到 git。

## 可选依赖

不同测试或 smoke test 可能需要以下可选组件：

- PostgreSQL、Redis：API 健康检查、数据库迁移、Celery 投递。
- Boltz2/ESMFold2 与 GPU：真实结构预测。
- IgGM、HMMER、GROMACS、gemmi：成熟、编号和 MD。
- RDKit、Open Babel、Meeko、Vina/GNINA：小分子及 RAS 对接。
- ESM/AntiFold、PyRosetta/Rosetta、RFdiffusion/ProteinMPNN：相应设计和评价模块。
- `external/ras-tricomplex-docking` 子模块与本地 `external/TNP` 对照依赖。

纯单元测试应优先使用临时目录和 mock；需要模型权重、GPU、网络或商业授权软件的检查应明确作为集成测试执行。

## Smoke test 目标

生产发布前至少确认：

1. `bash scripts/start_infra.sh` 后 PostgreSQL 和 Redis 健康。
2. `bash scripts/start_platform.sh` 后 API 与配置数量的 Celery Worker 存活。
3. `GET /api/health` 返回 HTTP 200，`database`、`redis` 为 `ok`。
4. 登录、任务列表和 Vue 静态资源可访问；页面使用 `frontend/dist/`，不是意外回退到 `web/`。
5. 提交一个最小、低成本的结构预测任务，状态能按 `queued → running → done` 流转。
6. 完成后结构文件和指标可下载，数据库中的结果索引指向实际输出目录。
7. 对本次发布涉及的专项模块，各提交一个最小输入，确认 Runner、外部可执行文件和输出解析正常。
8. `bash scripts/stop_platform.sh` 能停止 API 与 Worker，随后可正常重启。

真实模型 smoke test 可能消耗 GPU 和外部资源，必须在受控测试账号、测试输出目录中运行；不要把测试产物提交到仓库。
