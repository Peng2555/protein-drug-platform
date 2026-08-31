# affinity_redesign（模块）

本目录是 **`antibody_redesign` 仓库内的第一个模块**，负责抗体亲和力双轨改造：

- **序列轨**：ESM-1v 共识（主）+ 可选 ESM-2 探索（Hie et al., Nat Biotechnol 2023）
- **结构轨**：AntiFold 复合物 inverse folding 打分（Shanker et al., Science 2024）
- **结构复核**：Boltz2（相对 WT 的 ipTM）+ Rosetta 界面能
- **导出**：`ranked_mutations.csv` + 湿实验短名单

## 文档

- [PIPELINE.md](docs/PIPELINE.md) — 流程、两条入口、CLI
- [BOLTZ2_INTEGRATION.md](docs/BOLTZ2_INTEGRATION.md) — 接入 Boltz2 Web 的做法

## 端到端

```bash
affinity-redesign workflow --campaign runs/lycov1404_7mmo__demo --skip-round1
# 或
affinity-redesign workflow --from-fasta input.fasta --complex complex.pdb --slug my_ab
affinity-redesign workflow --from-fasta input.fasta --slug my_ab
```
