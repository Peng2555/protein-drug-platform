# 亲和力改造流程

## 总览

两条入口，后面共用：

```text
A) 序列 + 复合物 PDB/CIF
B) 仅序列  →  先 Boltz2 折 WT 复合物，写入 input/complex.pdb

        ↓
prepare（单点枚举 + 硬过滤）
        ↓
round1：PLM + AntiFold → merge tier A/B/C（默认全保留）
        ↓
rescore：对 WT + 全部 A/B/C 做 Boltz2 预测
        → 相对 WT 的 ΔipTM 门控
        → Rosetta FastRelax + 界面 ddG
        ↓
exports/
  ranked_mutations.csv     全表（含 decision / wetlab）
  wetlab_candidates.csv    建议送实验的短名单
  structures/              WT + 短名单 PDB
  summary.json
```

不含 AF3Score。Round2 组合仍要湿实验后另跑。

## CLI

```bash
# 入口 A：已有 campaign（含 sequences.fasta + complex.pdb）
affinity-redesign workflow --campaign runs/lycov1404_7mmo__demo

# 已跑过 round1，只补 Boltz2+Rosetta
affinity-redesign workflow --campaign runs/lycov1404_7mmo__demo --skip-round1

# 入口 B：只有 FASTA（H / L / A）
affinity-redesign workflow --from-fasta my.fasta --slug my_ab

# 入口 A 从文件新建
affinity-redesign workflow --from-fasta my.fasta --complex complex.pdb --slug my_ab
```

## 标准测试抗体

| 抗体 | PDB | 说明 |
|------|-----|------|
| **LY-CoV1404** | **7MMO** | Shanker et al. Science 2024；Fv(H/L)+RBD(A) |

## 筛选规则（rescore）

| 判定 | 条件 |
|------|------|
| drop | Boltz2 失败，或 ΔipTM < `delta_iptm_min`（默认 −0.03） |
| review | Boltz2 过门，但 Rosetta ddG > `max_ddg`（默认 3）或非 A 档 clash |
| keep / 进湿实验短名单 | Boltz2 未明显变差，且 ddG 可接受 |

阈值在 `configs/round1_default.yaml` 的 `rescore:`。

## 文献对照

- 序列轨：Hie et al., Nat Biotechnol 2023
- 结构轨：Shanker et al., Science 2024 / AntiFold
- 结构复核：Boltz2 ipTM（相对 WT）+ Rosetta InterfaceAnalyzer
