# 安装与环境准备

本文给出从空白 Linux 主机部署平台所需的组件总览。不同计算模块依赖互相冲突，建议使用独立 conda 环境，不要把所有模型和工具装入平台环境。

## 约定变量

以下示例只使用占位符；请按机器实际位置设置：

```bash
export PROJECT_ROOT="<项目目录>/protein-drug-platform"
export CONDA_ROOT="<conda 安装目录>"
export PLATFORM_ENV="<平台 conda 环境目录>"
export CACHE_ROOT="<模型缓存目录>"
export RUN_ROOT="<运行产物目录>"
```

不得把数据库密码、Token、`SECRET_KEY` 或私有仓库凭据写入文档或提交到 git。复制根目录 [`.env.example`](../.env.example) 为 `.env` 后，在本机替换其中路径、密码和密钥；`.env` 不提交。

## 1. 基础设施

主机需要 Git、Docker Engine（含 Compose 插件）和常用编译工具。PostgreSQL 16 与 Redis 7 可直接用仓库的 Compose 配置启动：

```bash
cd "${PROJECT_ROOT}"
bash scripts/start_infra.sh
cp -n .env.example .env
```

也可以使用外部托管的 PostgreSQL/Redis，只需在 `.env` 设置 `DATABASE_URL` 与 `REDIS_URL`。生产部署应使用独立强密码、限制监听地址并配置备份；不要沿用示例值。

## 2. Python 平台环境

建议使用 Python 3.11 的独立环境，并安装平台依赖和 Boltz2 CLI：

```bash
"${CONDA_ROOT}/bin/conda" create -p "${PLATFORM_ENV}" python=3.11 -y
"${PLATFORM_ENV}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements-platform.txt"
# 按所用 Boltz2 版本的官方安装方式安装 boltz，并确认命令可执行
"${PLATFORM_ENV}/bin/boltz" --help
```

将 `PY`、`BOLTZ_BIN`、`BOLTZ_CACHE`、`HF_HOME` 和 `TORCH_HOME` 等路径配置到本机环境或 `.env`。首次运行模型通常需要下载权重，离线服务器应提前准备缓存。

## 3. Node 与前端

构建脚本要求 Node.js 20+ 和 npm：

```bash
cd "${PROJECT_ROOT}/frontend"
npm ci
npm run build
```

也可在项目根目录运行 `bash scripts/build_frontend.sh`。生成的 `frontend/dist/` 可部署但不提交，源码位于 `frontend/src/`。

## 4. 外部 conda 环境与工具

只为实际启用的模块安装对应环境，并把可执行文件路径写入 `.env`：

| 模块 | 建议独立环境/工具 | 主要配置 |
|------|-------------------|----------|
| ESMFold2 | ESMFold2 Python 环境及模型缓存 | `ESMFOLD_PY`、`ESMFOLD_MODEL` |
| 亲和力成熟、MD | IgGM、HMMER、GROMACS、gemmi | `HMMER_PATH`、`GMX_BIN`、`GEMMI_PY` |
| 通用小分子对接 | RDKit、Open Babel、Meeko、Vina；可选 GNINA | `VINA_BIN`、`GNINA_BIN` |
| RAS 三元复合物对接 | Python 3.10 的 `ras-cadd` 环境及 RAS 子模块 | `RAS_DOCKING_ROOT`、`RAS_DOCKING_PYTHON` |
| Rosetta 评价 | PyRosetta 环境，或 Rosetta 二进制/Slurm 集群 | `PYROSETTA_PYTHON`、`ROSETTA_BIN_DIR`、`ROSETTA_CLUSTER_*` |
| Venus-MAXWELL | 独立 Python 环境和本地 checkpoint | `MAXWELL_PYTHON`、`MAXWELL_CKPT` |
| 亲和力改造 | ESM/PLM、AntiFold、可选 PyRosetta | 算法位于 `workflows/affinity_redesign/`，路径按本机环境配置 |
| 多肽遮蔽 | RFdiffusion、SE(3) 环境、ProteinMPNN | `RFDIFFUSION_ROOT`、`SE3NV_PYTHON`、项目根目录变量 |
| TNP profile | `external/TNP` 本地对照代码；其原始流程还涉及 Python 3.10、DSSP 等 | TNP 输出根目录及本地依赖路径 |

RAS 外部流程是正式 git submodule：

```bash
cd "${PROJECT_ROOT}"
git submodule update --init --recursive external/ras-tricomplex-docking
```

`external/TNP` 当前只是本地对照依赖，不是正式子模块；新主机不能假定 `git submodule update` 会提供它，应由维护者按授权来源单独准备。各专项模块的版本和安装细节以 `docs/` 下对应说明为准。

## 5. 路径与启动前检查

在 `.env` 中将所有输出目录设置到 `${RUN_ROOT}` 下或指向它的兼容链接，并确认平台用户可读写。至少检查：

```bash
test -x "${PLATFORM_ENV}/bin/python"
test -x "${PLATFORM_ENV}/bin/boltz"
test -f "${PROJECT_ROOT}/frontend/dist/index.html"
```

完成配置后，以生产入口启动：

```bash
cd "${PROJECT_ROOT}"
PY="${PLATFORM_ENV}/bin/python" bash scripts/start_platform.sh
bash scripts/status_platform.sh
```

`app/server.py` 与 `scripts/start_server.sh` 是 legacy 单机原型，不用于生产部署。
