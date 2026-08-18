# RAS 三元复合物对接模块

## 安装外部流程

```bash
mkdir -p external
git clone https://github.com/Peng2555/ras-tricomplex-docking.git \
  external/ras-tricomplex-docking
conda create -n ras-cadd python=3.10 -y
conda run -n ras-cadd pip install -r external/ras-tricomplex-docking/rmc6236_cadd/requirements.txt
```

把 `.env.example` 中的 `RAS_DOCKING_*` 和 `VINA_BIN` 配置复制到 `.env`。当前模块把每个任务复制到独立的输出目录执行，不会修改共享仓库。

## Web 中的工作阶段

- RMC-6236：fetch、prepare、redock、literature、screen、contacts
- RMC-6291：download、prepare、dock

`screen` 阶段需要通过 Web 上传 `candidates.sdf`。标准 Vina 使用 CPU；任务暂时复用现有 Celery 队列，但不会使用 GPU。

## 结果

任务完成后，`results_json` 会收集外部流程生成的 JSON、CSV 和结构文件索引，原始结果位于 `docking_outputs/<任务目录>/<项目>/`。
