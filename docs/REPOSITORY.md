# 仓库结构与提交规范

本文说明 BoltzFold 仓库里**什么应该进 git**、**什么必须忽略**，以及克隆后如何还原完整开发环境。

## 目录一览

| 路径 | 是否提交 | 说明 |
|------|----------|------|
| `app/` | ✅ | FastAPI 后端、各业务路由与服务 |
| `worker/` | ✅ | Celery 异步任务 |
| `workflows/*/` | ✅ | 算法源码的唯一仓库位置；根目录不保留同名源码兼容入口 |
| `scripts/` | ✅ | 预测/对接/MD/平台启停脚本；力场文件 `md_forcefields/` 需保留 |
| `frontend/src/` | ✅ | Vue 3 源码（不含自动生成 d.ts） |
| `frontend/public/` | ✅ | 静态公共资源（logo、favicon） |
| `frontend/dist/` | ❌ | `npm run build` 产物，部署前本地构建 |
| `frontend/node_modules/` | ❌ | `npm ci` 安装 |
| `web/` | ✅ | 旧版静态页（挂载在 `/legacy-app`） |
| `docs/` | ✅ | 模块集成与仓库说明 |
| `inputs/` | ✅ | 示例 FASTA 等小输入 |
| `external/ras-tricomplex-docking/` | 🔗 子模块 | RAS 三元复合物对接外部流程，见下文 |
| `external/TNP/` | 本地依赖 | TNP 上游代码的本地对照副本，当前不是正式子模块 |
| `run/` | ❌ | 所有任务运行结果与日志的实际目录 |
| `outputs/` 等 `*_outputs/`、`logs/` | ❌ | 兼容输出路径；多数目标为归入 `run/`，但部分路径当前仍可能是根目录实目录 |
| `HER2_domain_binding*.csv` | 分析产物 | HER2 domain binding 汇总结果，不是源码或固定输入 |
| `data/` | ❌ | 本地 SQLite 或运行时数据 |

## 提交信息

提交说明使用**简体中文**，专有名词可保留原文（Mol*、pLDDT、GROMACS 等）。

## 克隆与子模块

RAS 对接依赖独立仓库，以 **git submodule** 管理：

```bash
git clone https://github.com/Peng2555/protein-drug-platform.git
cd protein-drug-platform
git submodule update --init --recursive external/ras-tricomplex-docking
```

或克隆时一并拉子模块：

```bash
git clone --recurse-submodules https://github.com/Peng2555/protein-drug-platform.git
```

主仓库实际 remote 名称为 `protein-drug-platform.git`。上述地址不包含访问凭据；私有访问令牌应由 Git 凭据管理器或 SSH 代理提供。

子模块内的大型复现输出（`reproduction/output/` 等）在子模块自己的 `.gitignore` 中处理，**不要**提交到 Boltz2 主仓库。

`external/TNP/` 当前是本地对照依赖，不是 `.gitmodules` 管理的正式子模块。克隆主仓库后不能假定它会由 `git submodule update` 自动还原；如需运行 TNP profile，应按授权来源单独准备并核对版本。

## 每次提交应忽略的内容（速查）

完整规则见根目录 [`.gitignore`](../.gitignore)。

### 绝不上传

- **密钥**：`.env`、任何含密码/Token 的文件（只提交 `.env.example`）
- **任务产物**：`run/`，以及根目录兼容路径 `outputs/`、`md_outputs/`、`docking_outputs/`、`maturation_outputs/`、`synthesis_outputs/`、`developability_outputs/`、`hydro_redesign_outputs/`、`cic_profile_outputs/`、`tnp_profile_outputs/`
- **分析汇总**：根目录 `HER2_domain_binding.csv`、`HER2_domain_binding_iptm_max.csv` 等可重新生成的分析产物
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

`frontend/dist/` 是 Vue 生产构建产物，可以从 `frontend/src/`、`package.json` 和锁文件重建；`web/` 是 legacy 静态页面，只保留兼容访问。

## 运行目录现状与目标

长期目标是所有任务产物实际存放在 `run/`，根目录 `outputs/` 与各 `*_outputs/` 仅作为兼容链接，以适配 `.env` 和历史 `work_dir`。

这些输出兼容链接与源码布局无关，继续保留。`affinity_redesign`、`hydro_redesign`、`cic_profile`、`tnp_profile` 的算法源码只存放在 `workflows/` 下，根目录不再提供同名源码软链接。

当前部署中 `hydro_redesign_outputs/`、`cic_profile_outputs/`、`tnp_profile_outputs/` 仍可能是根目录实目录，而不是链接。清理、备份或迁移前必须先判断路径类型并确认内容已经复制到 `run/`，不得直接按“都是符号链接”处理。

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
