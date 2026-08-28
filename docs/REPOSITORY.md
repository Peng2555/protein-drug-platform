# 仓库结构与提交规范

本文说明 BoltzFold 仓库里**什么应该进 git**、**什么必须忽略**，以及克隆后如何还原完整开发环境。

## 目录一览

| 路径 | 是否提交 | 说明 |
|------|----------|------|
| `app/` | ✅ | FastAPI 后端、各业务路由与服务 |
| `worker/` | ✅ | Celery 异步任务 |
| `scripts/` | ✅ | 预测/对接/MD/平台启停脚本；力场文件 `md_forcefields/` 需保留 |
| `frontend/src/` | ✅ | Vue 3 源码（不含自动生成 d.ts） |
| `frontend/public/` | ✅ | 静态公共资源（logo、favicon） |
| `frontend/dist/` | ❌ | `npm run build` 产物，部署前本地构建 |
| `frontend/node_modules/` | ❌ | `npm ci` 安装 |
| `web/` | ✅ | 旧版静态页（挂载在 `/legacy-app`） |
| `docs/` | ✅ | 模块集成与仓库说明 |
| `inputs/` | ✅ | 示例 FASTA 等小输入 |
| `external/ras-tricomplex-docking/` | 🔗 子模块 | RAS 三元复合物对接外部流程，见下文 |
| `outputs/` 等 `*_outputs/` | ❌ | 所有任务运行结果（含 `rosetta_eval_outputs/`） |
| `logs/` | ❌ | API / Celery 日志与 pid |
| `data/` | ❌ | 本地 SQLite 或运行时数据 |

## 提交信息

提交说明使用**简体中文**，专有名词可保留原文（Mol*、pLDDT、GROMACS 等）。

## 克隆与子模块

RAS 对接依赖独立仓库，以 **git submodule** 管理：

```bash
git clone https://github.com/Peng2555/Boltz2.git
cd Boltz2
git submodule update --init --recursive external/ras-tricomplex-docking
```

或克隆时一并拉子模块：

```bash
git clone --recurse-submodules https://github.com/Peng2555/Boltz2.git
```

子模块内的大型复现输出（`reproduction/output/` 等）在子模块自己的 `.gitignore` 中处理，**不要**提交到 Boltz2 主仓库。

## 每次提交应忽略的内容（速查）

完整规则见根目录 [`.gitignore`](../.gitignore)。

### 绝不上传

- **密钥**：`.env`、任何含密码/Token 的文件（只提交 `.env.example`）
- **任务产物**：`outputs/`、`md_outputs/`、`docking_outputs/`、`maturation_outputs/`、`synthesis_outputs/`、`developability_outputs/`
- **结构/轨迹**：`*.cif`、`*.pdb`、`*.npz`、`*.gro`、`*.xtc` 等
- **模型权重**：`*.ckpt`、`*.pt`、`weights/`
- **前端构建**：`frontend/dist/`、`frontend/node_modules/`
- **日志**：`logs/`、`*.log`、`*.pid`
- **本地数据库**：`data/`、`*.db`

### 不要手动提交（工具会自动生成）

- `frontend/src/auto-imports.d.ts` — unplugin-auto-import
- `frontend/src/components.d.ts` — unplugin-vue-components
- `__pycache__/`、`.pytest_cache/` 等 Python 缓存

### 应该提交

- Python / TypeScript / Vue **源码**
- `requirements-*.txt`、`frontend/package.json` + `package-lock.json`
- `scripts/md_forcefields/` — GROMACS CHARMM36 力场（MD 模块依赖）
- `docker-compose.yml`、`.env.example`、`scripts/*.sh`（除本地 `docker_rootless.env`）
- 文档与示例输入

## 本地配置文件

| 文件 | 提交？ | 用法 |
|------|--------|------|
| `.env.example` | ✅ | 复制为 `.env` 后修改 |
| `.env` | ❌ | 数据库、Redis、密钥、各 conda 路径 |
| `scripts/docker_rootless.env.example` | ✅ | 复制为 `docker_rootless.env`，改 UID |
| `scripts/docker_rootless.env` | ❌ | 机器相关的 rootless Docker socket |

## 前端部署流程

API 优先挂载 `frontend/dist/`。更新前端后：

```bash
bash scripts/build_frontend.sh
bash scripts/stop_platform.sh && bash scripts/start_platform.sh
```

`start_platform.sh` 在检测到 `dist/` 缺失时会提示运行上述构建脚本。

## 提交前自检

```bash
# 查看将要提交的文件
git status

# 确认没有误加产物/密钥
git diff --cached --name-only | rg -i '\.(cif|pdb|npz|log|env|ckpt)$|outputs/|dist/|node_modules/'

# 不应有输出；若有，git restore --staged <file>
```

## 已从仓库清理的内容（维护记录）

- Vite 自动生成的 `auto-imports.d.ts` / `components.d.ts`（改由 `.gitignore` 忽略）
- 机器专属 `scripts/docker_rootless.env`（改为 `.example` 模板）
- 未使用的 Vite 默认图标 `vite.svg` / `vue.svg` / `hero.png`
- 旧版 3Dmol vendor（已迁移 Mol*）

## 旧版页面

`web/` 仍保留供 `/legacy-app` 访问；新功能优先在 `frontend/` 开发。两者 logo 路径不同，暂保留双份 `biocytogen-logo.png`。
