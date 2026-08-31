# 示例：LY-CoV1404（PDB 7MMO）

Shanker et al., *Science* 2024 使用的临床抗体。

## 准备结构

```bash
# 下载并截取 Fv(H/L)+RBD(A)，写入 runs/ 下某 campaign 的 input/complex.pdb
# 仓库内脚本：
bash scripts/prepare_lycov1404_7mmo.sh runs/lycov1404_7mmo__demo
```

序列已放在本目录 `sequences.fasta`（与截取后的 PDB 链一致）。
