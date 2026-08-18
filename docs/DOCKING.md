# 通用小分子对接

Web 入口是 `/docking`。用户提供：

- 受体：PDB、PDBQT 或 mmCIF
- 小分子：**SMILES 结构式**（不是分子式，也不是配体三维文件）
- 搜索盒中心和尺寸（Å），或上传参考配体自动计算搜索盒

流程：

1. 解析 SMILES，丢弃任何三维坐标
2. RDKit ETKDGv3 采样构象（默认 128），MMFF94s 优化，TFD 聚类
3. 选取若干独立簇代表作为对接起点（默认 10）
4. Meeko 准备配体 PDBQT（大环默认可转动；失败时回退 Open Babel）
5. 对每个起点做 **全局** AutoDock Vina（禁止 `--local_only`）
6. 把所有起点的 poses 按 Vina 分数合并排序，用全局 Top1 生成复合物

默认参数与 CPU 验证流程一致：exhaustiveness=8，num_modes=20，energy_range=5 kcal/mol。

参考配体只用于定位口袋，不作为对接起点。

输出保存在 `DOCKING_OUT_ROOT` 对应的任务目录中。表中 RMSD 下/上界是相对该次 Vina 起点的，不是相对晶体。
