import type { ModuleId } from '@/utils/platform'

export type ToolModality = 'protein' | 'antibody' | 'peptide' | 'enzyme' | 'small_molecule'
export type ToolFunction =
  | 'structure_prediction'
  | 'inverse_folding'
  | 'developability'
  | 'antibody_design'
  | 'docking'
  | 'md'
  | 'utilities'
export type ToolInput = 'fasta' | 'pdb' | 'sdf' | 'csv'

export interface PlatformTool {
  id: string
  name: string
  moduleId: ModuleId
  route: string
  function: ToolFunction
  modalities: ToolModality[]
  inputs: ToolInput[]
  description: string
  citation?: string
  duration: string
  isNew?: boolean
  engines?: string[]
}

export const TOOL_MODALITY_LABELS: Record<ToolModality, string> = {
  protein: '蛋白',
  antibody: '抗体',
  peptide: '多肽',
  enzyme: '酶',
  small_molecule: '小分子',
}

export const TOOL_FUNCTION_LABELS: Record<ToolFunction, string> = {
  structure_prediction: '结构预测',
  inverse_folding: '逆折叠设计',
  developability: '可开发性',
  antibody_design: '抗体设计',
  docking: '蛋白-配体对接',
  md: '分子动力学',
  utilities: '实用工具',
}

export const TOOL_INPUT_LABELS: Record<ToolInput, string> = {
  fasta: 'FASTA',
  pdb: 'PDB',
  sdf: 'SDF',
  csv: 'CSV',
}

export const PLATFORM_TOOLS: PlatformTool[] = [
  {
    id: 'boltz2',
    name: 'Boltz-2',
    moduleId: 'fold',
    route: '/fold/new',
    function: 'structure_prediction',
    modalities: ['protein', 'antibody', 'peptide', 'enzyme', 'small_molecule'],
    inputs: ['fasta'],
    description: '复合物结构预测，支持蛋白、多肽与小分子共折叠。',
    citation: 'Boltz team',
    duration: '5–30 分钟',
    engines: ['Boltz2'],
  },
  {
    id: 'esmfold2',
    name: 'ESMFold2',
    moduleId: 'fold',
    route: '/fold/new',
    function: 'structure_prediction',
    modalities: ['protein', 'antibody', 'peptide', 'enzyme'],
    inputs: ['fasta'],
    description: '快速预测蛋白与复合物结构，适合大批量序列折叠。',
    citation: 'Candido et al.',
    duration: '5–30 分钟',
    isNew: true,
    engines: ['ESMFold2'],
  },
  {
    id: 'protein_mpnn',
    name: 'ProteinMPNN',
    moduleId: 'design',
    route: '/design/new',
    function: 'inverse_folding',
    modalities: ['protein', 'antibody', 'peptide', 'enzyme'],
    inputs: ['pdb'],
    description: '固定骨架的序列设计，适用于界面与活性位点优化。',
    citation: 'Dauparas et al.',
    duration: '5–30 分钟',
  },
  {
    id: 'rosetta',
    name: 'Rosetta 结构评价',
    moduleId: 'rosetta',
    route: '/rosetta/new',
    function: 'developability',
    modalities: ['protein', 'antibody', 'peptide'],
    inputs: ['pdb'],
    description: '约束 Relax、界面 ΔΔG 与 ranking.csv 多指标排序。',
    citation: 'PyRosetta',
    duration: '5–30 分钟',
  },
  {
    id: 'esm2_dev',
    name: 'ESM-2 可开发性',
    moduleId: 'developability',
    route: '/developability/new',
    function: 'developability',
    modalities: ['protein', 'antibody'],
    inputs: ['fasta'],
    description: '序列可开发性打分与改造建议，辅助稳定性与溶解度评估。',
    duration: '1–5 分钟',
  },
  {
    id: 'iggm',
    name: 'IgGM',
    moduleId: 'maturation',
    route: '/maturation/new',
    function: 'antibody_design',
    modalities: ['antibody'],
    inputs: ['pdb', 'fasta'],
    description: 'CDR 变体采样与亲和力成熟，生成抗体突变候选。',
    citation: 'Wang et al.',
    duration: '5–30 分钟',
  },
  {
    id: 'synthesis',
    name: '合成候选筛选',
    moduleId: 'synthesis',
    route: '/synthesis/new',
    function: 'utilities',
    modalities: ['antibody'],
    inputs: ['csv'],
    description: '测序表与突变表交叉筛选，输出合成优先级候选。',
    duration: '1–5 分钟',
  },
  {
    id: 'vina',
    name: 'AutoDock Vina',
    moduleId: 'docking',
    route: '/docking/new',
    function: 'docking',
    modalities: ['enzyme', 'small_molecule'],
    inputs: ['pdb', 'sdf'],
    description: '口袋检测引导的盲对接，可视化结合模式与打分排序。',
    citation: 'J. Eberhardt et al.',
    duration: '秒级–5 分钟',
  },
  {
    id: 'gromacs',
    name: 'GROMACS MD',
    moduleId: 'md',
    route: '/md/new',
    function: 'md',
    modalities: ['protein', 'small_molecule'],
    inputs: ['pdb'],
    description: '显式溶剂分子动力学，验证对接复合物结合稳定性。',
    duration: '30–60 分钟',
  },
]
