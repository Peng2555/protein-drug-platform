import type { ModuleId } from '@/utils/platform'

export type ScenarioId = 'vhh' | 'antibody' | 'small_molecule' | 'general'

export interface ScenarioDef {
  id: ScenarioId
  label: string
  headline: string
  summary: string
  highlights: string[]
  primaryCta: { label: string; route: string }
  pipeline: { title: string; description: string }[]
}

export interface ScenarioDetailContent {
  intro: string
  pipeline: { title: string; description: string }[]
  outputs: string[]
}

export interface WorkflowStep {
  label: string
}

export interface WorkflowDef {
  id: string
  title: string
  description: string
  steps: WorkflowStep[]
  ctaLabel: string
  ctaRoute: string
  accent: 'teal' | 'blue' | 'cyan' | 'violet'
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: 'vhh',
    label: '纳米抗体 VHH',
    headline: '从 WT 结构到突变体排序',
    summary: '面向 VHH–抗原复合物：批量折叠、Rosetta 界面评价与合成候选筛选。',
    highlights: [
      'Boltz2 / ESMFold2 批量预测复合物结构',
      'PyRosetta 约束 Relax + 界面 ΔΔG 排序',
      'IgGM 亲和力成熟与合成候选交叉筛选',
    ],
    primaryCta: { label: '开始 VHH 结构预测', route: '/fold/new' },
    pipeline: [
      { title: '提交序列', description: '上传 VHH 与抗原 FASTA，或从已有折叠任务导入。' },
      { title: '批量折叠', description: 'Boltz2 预测复合物，查看 ipTM 与界面置信度。' },
      { title: 'Rosetta 评价', description: '相对 WT 的 ΔΔG / ΔE 多指标排序。' },
      { title: '实验候选', description: '导出 Top 突变体 relaxed 结构。' },
    ],
  },
  {
    id: 'antibody',
    label: '抗体复合物',
    headline: '复合物结构与设计优化',
    summary: 'IgG / 双链复合物折叠、序列设计与界面分析。',
    highlights: [
      '抗体–抗原复合物高精度折叠',
      'ProteinMPNN 界面序列设计',
      'Rosetta 突变体界面能对比',
    ],
    primaryCta: { label: '预测抗体复合物', route: '/fold/new' },
    pipeline: [
      { title: '复合物折叠', description: '抗体 + 抗原多链复合物结构预测。' },
      { title: '界面分析', description: '3D 查看、界面残基与相互作用表。' },
      { title: '序列设计', description: 'ProteinMPNN 固定骨架设计界面序列。' },
      { title: '再验证', description: '再折叠或 Rosetta 对比 WT。' },
    ],
  },
  {
    id: 'small_molecule',
    label: '小分子筛选',
    headline: '对接初筛到时序验证',
    summary: '口袋引导盲对接快速评估配体，GROMACS MD 复核结合稳定性。',
    highlights: [
      '口袋检测 + AutoDock Vina 盲对接',
      '结合模式可视化与打分排序',
      'GROMACS 显式溶剂 MD 稳定性验证',
    ],
    primaryCta: { label: '开始分子对接', route: '/docking/new' },
    pipeline: [
      { title: '受体准备', description: '上传蛋白 PDB，自动检测口袋。' },
      { title: '配体对接', description: 'Vina 盲对接，输出结合模式与打分。' },
      { title: 'MD 验证', description: 'GROMACS 短模拟看 RMSD 与稳定性。' },
    ],
  },
  {
    id: 'general',
    label: '通用蛋白',
    headline: '单蛋白结构与序列设计',
    summary: '单链/多链结构预测与 ProteinMPNN 序列设计。',
    highlights: [
      '单链与多链复合物结构预测',
      'pLDDT / ipTM 置信度评估',
      '骨架约束下的序列设计',
    ],
    primaryCta: { label: '提交序列预测', route: '/fold/new' },
    pipeline: [
      { title: '序列输入', description: '单链或多链 FASTA。' },
      { title: '结构预测', description: 'Boltz2 / ESMFold2 生成三维结构。' },
      { title: '序列设计', description: '可选 ProteinMPNN 设计变体。' },
    ],
  },
]

export const SCENARIO_DETAILS: Record<ScenarioId, ScenarioDetailContent> = {
  vhh: {
    intro: '面向纳米抗体研发：从抗原复合物预测到突变体界面排序，再到合成候选收敛。',
    pipeline: SCENARIOS[0].pipeline,
    outputs: ['复合物 PDB/CIF', 'ranking.csv / scores.csv', 'relaxed_structures/', 'report.html'],
  },
  antibody: {
    intro: 'IgG / 双链抗体与抗原的复合物建模、界面分析与序列设计闭环。',
    pipeline: SCENARIOS[1].pipeline,
    outputs: ['复合物结构', '界面指标', '设计序列候选', 'Rosetta 排名'],
  },
  small_molecule: {
    intro: '从 hit 对接到 MD 稳定性验证的小分子筛选流程。',
    pipeline: SCENARIOS[2].pipeline,
    outputs: ['对接 pose', 'Vina 打分', 'MD 轨迹', 'RMSD 曲线'],
  },
  general: {
    intro: '通用蛋白结构预测与序列设计入口。',
    pipeline: SCENARIOS[3].pipeline,
    outputs: ['预测结构', 'pLDDT 图', 'MPNN 序列'],
  },
}

export function scenarioById(id: string): ScenarioDef | undefined {
  return SCENARIOS.find((s) => s.id === id)
}

/** 各场景下高亮模块（能力地图默认筛选） */
export const SCENARIO_MODULES: Record<ScenarioId, ModuleId[]> = {
  vhh: ['fold', 'rosetta', 'maturation', 'synthesis', 'developability', 'design'],
  antibody: ['fold', 'design', 'rosetta', 'developability', 'maturation'],
  small_molecule: ['docking', 'md'],
  general: ['fold', 'design'],
}

export const WORKFLOWS_BY_SCENARIO: Record<ScenarioId, WorkflowDef[]> = {
  vhh: [
    {
      id: 'vhh-mutation-screen',
      title: '突变体界面筛选',
      description: '批量预测突变体复合物，Rosetta Relax + InterfaceAnalyzer 相对 WT 排序。',
      steps: [{ label: '结构预测' }, { label: '结构评价' }, { label: '查看排名' }],
      ctaLabel: '开始结构预测',
      ctaRoute: '/fold/new',
      accent: 'teal',
    },
    {
      id: 'vhh-maturation',
      title: '亲和力成熟',
      description: 'IgGM 对 CDR 采样变体，再折叠或 Rosetta / MD 复核候选。',
      steps: [{ label: 'IgGM 采样' }, { label: '再折叠' }, { label: '复核排名' }],
      ctaLabel: '进入亲和力改造',
      ctaRoute: '/affinity-redesign/new',
      accent: 'blue',
    },
    {
      id: 'vhh-developability',
      title: '序列可开发性',
      description: 'ESM-2 / MAXWELL 并列打分，筛选更稳、更易表达的变体序列。',
      steps: [{ label: '序列改造' }, { label: '结构预测' }, { label: '对比指标' }],
      ctaLabel: '进入序列改造',
      ctaRoute: '/developability/new',
      accent: 'violet',
    },
    {
      id: 'vhh-synthesis',
      title: '合成候选筛选',
      description: '测序表与突变表交叉筛选，收敛到可下单验证的候选。',
      steps: [{ label: '导入表' }, { label: '交叉筛选' }, { label: '导出候选' }],
      ctaLabel: '进入合成候选',
      ctaRoute: '/synthesis/new',
      accent: 'cyan',
    },
  ],
  antibody: [
    {
      id: 'ab-fold-analyze',
      title: '复合物折叠与分析',
      description: 'Boltz2 / ESMFold2 预测抗体–抗原复合物，查看 ipTM 与界面指标。',
      steps: [{ label: '复合物折叠' }, { label: '界面分析' }, { label: '结构下载' }],
      ctaLabel: '开始结构预测',
      ctaRoute: '/fold/new',
      accent: 'teal',
    },
    {
      id: 'ab-design',
      title: '界面序列设计',
      description: 'ProteinMPNN 在固定骨架下设计序列，再折叠验证。',
      steps: [{ label: '序列设计' }, { label: '再折叠' }, { label: '对比 WT' }],
      ctaLabel: '进入序列设计',
      ctaRoute: '/design/new',
      accent: 'blue',
    },
    {
      id: 'ab-rosetta',
      title: '突变体 Rosetta 评价',
      description: '对设计或突变体批量做约束 FastRelax 与 ΔΔG 排序。',
      steps: [{ label: '选折叠结果' }, { label: '结构评价' }, { label: 'Top 候选' }],
      ctaLabel: '进入结构评价',
      ctaRoute: '/rosetta/new',
      accent: 'violet',
    },
  ],
  small_molecule: [
    {
      id: 'ligand-dock',
      title: '对接初筛',
      description: 'CB-Dock 思路：口袋检测 + Vina 盲对接，快速评估结合模式。',
      steps: [{ label: '上传受体' }, { label: '配体对接' }, { label: '结合模式' }],
      ctaLabel: '开始分子对接',
      ctaRoute: '/docking/new',
      accent: 'cyan',
    },
    {
      id: 'ligand-md',
      title: 'MD 稳定性验证',
      description: 'GROMACS 显式溶剂短模拟，复核对接 pose 是否稳定。',
      steps: [{ label: '选对接结果' }, { label: 'MD 模拟' }, { label: 'RMSD / 能量' }],
      ctaLabel: '进入 MD 验证',
      ctaRoute: '/md/new',
      accent: 'teal',
    },
  ],
  general: [
    {
      id: 'protein-fold',
      title: '蛋白结构预测',
      description: '单链或多链序列 → Boltz2 / ESMFold2 三维结构。',
      steps: [{ label: '提交序列' }, { label: '等待折叠' }, { label: '3D 查看' }],
      ctaLabel: '开始结构预测',
      ctaRoute: '/fold/new',
      accent: 'teal',
    },
    {
      id: 'protein-design',
      title: '骨架约束序列设计',
      description: 'ProteinMPNN 在给定骨架上生成序列候选。',
      steps: [{ label: '上传结构' }, { label: 'MPNN 设计' }, { label: '候选序列' }],
      ctaLabel: '进入序列设计',
      ctaRoute: '/design/new',
      accent: 'blue',
    },
  ],
}

/** 模块 → 底层引擎展示名 */
export const MODULE_ENGINES: Partial<Record<ModuleId, string>> = {
  fold: 'Boltz2 · ESMFold2',
  design: 'ProteinMPNN',
  rosetta: 'PyRosetta',
  developability: 'ESM-2 · MAXWELL',
  maturation: 'IgGM',
  affinity_redesign: 'round1 · Boltz2 · Rosetta',
  synthesis: '表交叉筛选',
  docking: 'AutoDock Vina',
  md: 'GROMACS',
}
