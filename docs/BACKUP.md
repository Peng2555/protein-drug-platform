# 备份与回滚

平台需要备份两类不可重建数据：PostgreSQL 元数据和任务运行目录。源码应由 git 保存，`frontend/dist/` 可由源码重新构建。

## 备份范围

- PostgreSQL：用户、任务状态、参数和结果索引。
- 运行产物：目标目录 `run/`，以及仍为根目录实目录的各 `*_outputs/`。
- 本机配置：`.env` 可加密后存入受控的密钥/备份系统，但不得提交到 git 或写入本文。
- 可选模型缓存和商业工具：通常可重新安装；若下载或授权恢复困难，应按组织策略单独备份。

`frontend/dist/`、`frontend/node_modules/`、Python 缓存和日志不是核心备份对象。`frontend/dist/` 应使用锁定的 Node 依赖从 `frontend/src/` 重建。

## PostgreSQL 备份

从 `.env` 或密钥系统读取连接信息，不要把密码直接放进命令历史。示例变量：

```bash
export BACKUP_ROOT="<备份目录>"
export PGHOST="<数据库主机>"
export PGPORT="<数据库端口>"
export PGDATABASE="<数据库名>"
export PGUSER="<数据库用户>"
export PG_DUMP_FILE="${BACKUP_ROOT}/postgres-<时间戳>.dump"
mkdir -p "${BACKUP_ROOT}"
pg_dump --format=custom --no-owner --no-acl --file="${PG_DUMP_FILE}"
pg_restore --list "${PG_DUMP_FILE}" >/dev/null
```

`pg_dump` 会使用标准 libpq 认证方式，例如交互输入、权限受限的 `.pgpass` 或外部密钥注入。不要在脚本中写真实密码。

若 PostgreSQL 运行在仓库 Compose 容器中，也可通过 `docker compose exec -T postgres pg_dump ...` 导出到宿主机；数据库名和用户仍应来自本机配置。

## PostgreSQL 恢复

优先恢复到空数据库并先验证，不要直接覆盖唯一生产库：

```bash
export PG_RESTORE_FILE="<备份 dump 路径>"
createdb "<待恢复数据库>"
pg_restore \
  --clean --if-exists --no-owner --no-acl \
  --dbname="<待恢复数据库>" \
  "${PG_RESTORE_FILE}"
```

恢复完成后运行只读核对：用户数、任务数、最近任务状态，以及任务记录中的输出路径是否存在。切换应用连接前保留原数据库。

## 运行目录备份

先停止 API 和 Worker，避免数据库状态与正在写入的文件不一致：

```bash
cd "<项目目录>"
bash scripts/stop_platform.sh
```

使用支持权限、时间戳和链接的工具备份：

```bash
rsync -aH --numeric-ids "<项目目录>/run/" "<备份目录>/run/"
```

当前 `hydro_redesign_outputs/`、`cic_profile_outputs/`、`tnp_profile_outputs/` 等路径仍可能是根目录实目录。备份前用 `test -L`/`test -d` 逐一确认；凡是实目录都要单独纳入备份，不能只复制 `run/`。兼容符号链接本身可以重建，但备份工具不得误将链接外的数据漏掉。

建议为数据库 dump 和文件快照使用同一时间戳，并生成校验和。恢复演练应验证结构文件、指标 JSON、下载接口和至少一个历史任务页面。

## 回滚顺序

1. 停止 API 和 Celery Worker，暂停新任务进入系统。
2. 保存当前故障现场：数据库 dump、运行目录增量和日志。
3. 回滚源码到已验证版本，并恢复该版本匹配的 `.env` 配置。
4. 恢复运行目录；保留原目录副本，不在原地破坏性覆盖。
5. 恢复 PostgreSQL 到新库，核对记录与文件路径后再切换 `DATABASE_URL`。
6. 使用 `npm ci && npm run build` 重建 `frontend/dist/`。
7. 启动基础设施和生产入口，检查 `/api/health`、Worker、历史任务下载。
8. 完成 smoke test 后再恢复用户访问和任务提交。

当仅回滚前端时，不需要恢复数据库和运行目录；重新构建并重启生产 API 即可。涉及数据库结构或任务输出格式的版本回滚必须成套恢复，避免旧代码读取新格式数据。
