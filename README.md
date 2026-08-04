# BoltzFold — 蛋白质结构预测平台

**给序列 → 队列调度 → Boltz2 预测 → 网页查看 / 下载**

支持：用户登录、任务历史、异步 GPU Worker、3D 结构查看（3Dmol.js）。

---

## 架构

```
浏览器 (web/)
    ↓ REST + JWT
FastAPI (app/main.py)
    ↓ enqueue
Redis + Celery Worker (worker/tasks.py)
    ↓ subprocess
boltz_runner.py → pred.cif
    ↓
PostgreSQL（任务元数据）+ outputs/（结构文件）
```

---

## 快速启动

### 0. Docker Rootless（无 sudo / 无 docker 组）

本机已配置 **Docker Rootless**，脚本会自动加载 `scripts/docker_rootless.env`。

首次安装（已完成可跳过）：
```bash
dockerd-rootless-setuptool.sh install
# 开机自启 Docker（可选，需管理员一次）：
# sudo loginctl enable-linger pengpai
```

手动使用 docker 前：
```bash
source scripts/docker_rootless.env
docker ps
```

### 1. 基础设施（PostgreSQL + Redis）

```bash
cd /home/pengpai/data/Company_Project/Boltz2
bash scripts/start_infra.sh   # docker compose up
cp .env.example .env            # 首次
```

### 2. 一键启动平台（API + Celery Worker）

```bash
bash scripts/start_platform.sh
# 或（脚本已 chmod +x 后）：
./scripts/start_platform.sh

# 停止 / 查看状态：
bash scripts/stop_platform.sh
bash scripts/status_platform.sh
# 浏览器打开（见脚本输出的地址）：
#   本机:     http://127.0.0.1:8765
#   其他电脑: http://<服务器IP>:8765   （不要用 127.0.0.1）
```

默认管理员（首次 `init_db` 创建）：
- 用户名：`admin`
- 密码：`admin123`（请尽快修改）

### 3. 无 Docker 原型模式

不启动 Docker 时，默认使用 **SQLite**（`data/boltzfold.db`）+ 仍需 **Redis** 给 Celery。

```bash
# 仅 Redis（或改 REDIS_URL 指向已有实例）
docker compose up -d redis

# 编辑 .env：注释 DATABASE_URL 行即回退 SQLite
bash scripts/start_platform.sh
```

---

## 目录

```
Boltz2/
├── app/                    # FastAPI 后端
│   ├── main.py
│   ├── models.py           # User, Job
│   ├── routers/            # auth, jobs
│   └── celery_app.py
├── worker/tasks.py         # Celery 预测任务
├── scripts/
│   ├── boltz_runner.py     # 核心预测逻辑
│   ├── fold_fasta.py       # CLI（无需 Web）
│   ├── init_db.py
│   ├── start_infra.sh
│   └── start_platform.sh
├── web/                    # 前端（登录 / 提交 / 3D）
├── docker-compose.yml
├── outputs/                # 结构文件 {job_uuid}/
└── data/                   # SQLite（可选）
```

---

## 命令行（仍可用）

```bash
/home/pengpai/data/envs/boltz2/bin/python scripts/fold_fasta.py \
  -i inputs/example_vhh_lysozyme.fasta -o outputs/
```

---

## API 示例

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8765/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://127.0.0.1:8765/api/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fasta": ">H\nSEQ...\n>A\nSEQ...", "name": "test"}'

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/jobs
```

---

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串；不设则用 SQLite |
| `REDIS_URL` | Celery 队列 |
| `SECRET_KEY` | JWT 密钥 |
| `BOLTZ2_OUT_ROOT` | 结构输出目录 |
| `ADMIN_USERNAME/PASSWORD` | 首次初始化管理员 |
| `CELERY_GPU_COUNT` | GPU Worker 数量（默认 4，每卡 1 进程） |
| `CELERY_GPU_QUEUE` | 统一任务队列名（默认 `gpu`，折叠+MD 共用） |
| `MAX_JOBS_PER_USER_QUEUED` | 每用户排队上限；`0`=不限制，任务可一直入队直到 Worker 消化 |

---

## 多人并发与 GPU 占满策略

平台启动 **4 个 GPU Worker**（GPU 0–3 各 1 进程），**折叠与 MD 共用同一队列 `gpu`**：

- 队列里 **≥4 个任务** 时，4 张卡 **同时跑满**
- 任务 **少于 4 个** 时，只占用对应数量 GPU（正常）
- **不再**单独占用 GPU 0 的 MD Worker，避免空卡
- 单用户可连续提交/批量入队，Worker 按 FIFO 自动拉取（批量任务、单条任务一致）

```bash
bash scripts/status_platform.sh   # 看 queue / running / nvidia-smi
```

修改 GPU 数量：`.env` 中 `CELERY_GPU_COUNT=2` 后重启平台。

---

## MD 界面验证（GROMACS）

侧边栏 **MD 验证** 模块：从已完成 Boltz2 任务或上传 CIF/PDB 发起 GROMACS 显式溶剂 MD。

| 变量 | 说明 |
|------|------|
| `MD_PRODUCTION_NS` | 生产模拟时长（默认 **1 ns** MVP；生产可改为 100） |
| `MD_REPLICAS` | 复本数（默认 1） |
| `GMX_BIN` / `GEMMI_PY` | GROMACS / CIF 转换（IgGM 环境） |

API：`POST /api/md-jobs`、`POST /api/md-jobs/upload`、`GET /api/md-jobs/{id}`

输出目录：`md_outputs/{任务名}__{uuid}/`

---

## 生产建议

- 修改 `SECRET_KEY` 与 admin 密码
- 按机器 GPU 数设置 `CELERY_GPU_COUNT`
- Nginx 反代 + HTTPS
- 定期清理 `outputs/`、`md_outputs/` 旧任务

---

## 旧版 MVP

`app/server.py` + `scripts/start_server.sh` 为无数据库的单机版，已被本平台替代。
