# 蛋白质-药物计算平台

结构预测 · 序列改造 · 小分子对接 · 亲和力成熟 · MD 验证

把抗体或复合物序列交给平台，任务进入 GPU 队列，完成后在网页里看 3D、下结构和后续分析。账号登录、任务历史、四卡并行都已接好。

局域网默认打开 [http://192.168.8.25:8765/](http://192.168.8.25:8765/)，本机则是 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。


## 能做什么

**结构预测**　粘贴 FASTA 或批量 VHH，用 Boltz2 / ESMFold2 出复合物结构，网页里用 Mol* 查看。

**序列改造**　本地 ESM-2 3B 标出可以突变的位点、以及能换成哪些氨基酸。亲水性用 Kyte–Doolittle 差值标注，不在这一步替你做决定。

**小分子对接**　受体结构 + 配体 SMILES，ETKDG 采样后全局 Vina。

**亲和力成熟**　IgGM 在指定 CDR 上采样变体，再汇总去重。

**亲和力改造**　算法在仓库 `affinity_redesign/`：PLM + AntiFold 双轨，再 Boltz2 / Rosetta 重打分。Web 提交即可，无需再克隆外部 `antibody_redesign`。仍需本机 ESM / AntiFold / PyRosetta 环境。

**合成筛选**　把 IgGM 结果和测序表对齐，筛可下单序列。

**MD 验证**　从已完成折叠或上传的 CIF/PDB 发起 GROMACS 显式溶剂模拟。


## 怎么跑

第一次先准备好 PostgreSQL 和 Redis，再复制环境文件：

    bash scripts/start_infra.sh
    cp .env.example .env

之后日常只用：

    bash scripts/start_platform.sh
    bash scripts/status_platform.sh
    bash scripts/stop_platform.sh

脚本会打印本机和局域网地址。别的电脑请用服务器 IP，不要用 127.0.0.1。

首次初始化会有管理员账号 `admin` / `admin123`，请尽快改掉。没有 Docker 时可以只用 SQLite（注释掉 `.env` 里的 `DATABASE_URL`），Celery 仍然需要 Redis。


## 任务怎么走

浏览器带着 JWT 打 FastAPI，任务进 Redis 队列，每张 GPU 一个 Celery Worker 拉任务，结构写到 `outputs/`，元数据进 PostgreSQL。折叠和 MD 共用队列 `gpu`。四张卡都有活时会跑满；任务少于四条就只占对应数量的卡。

改 GPU 数量：在 `.env` 里设 `CELERY_GPU_COUNT`，然后重启平台。排队是否设上限看 `MAX_JOBS_PER_USER_QUEUED`（`0` 表示不限制）。


## 主要目录

`app/` 是 FastAPI 与各模块路由，`worker/` 是 Celery 任务，`scripts/` 里是预测、对接、ESM-2、平台启停脚本。前端在 `frontend/`（部署前需 `bash scripts/build_frontend.sh` 生成 `frontend/dist/`）。运行产物都在本地：`outputs/`、`md_outputs/`、`docking_outputs/` 等，**不会进 git**——详见 [docs/REPOSITORY.md](docs/REPOSITORY.md)。

克隆后若使用 RAS 对接，需初始化子模块：

    git submodule update --init external/ras-tricomplex-docking

命令行折叠仍然可用：

    /home/pengpai/data/envs/boltz2/bin/python scripts/fold_fasta.py -i inputs/example_vhh_lysozyme.fasta -o outputs/


## 环境与安全

`.env` 里需要关心的主要是数据库和 Redis 地址、`SECRET_KEY`、输出目录、管理员账号，以及 `CELERY_GPU_COUNT`、`GMX_BIN` 这类路径。生产环境务必改密钥和密码，按实际卡数设 Worker，前面加 Nginx + HTTPS。旧任务目录可以定期清。

用户注册默认需要管理员审批：`bash scripts/manage_users.sh list --pending`。


## 旧版

`app/server.py` 是无数据库的单机原型，已被当前平台替代。
