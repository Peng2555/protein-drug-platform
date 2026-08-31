import type { ModuleId } from '@/utils/platform'
export type PipelineSceneId = 'all' | 'antibody' | 'peptide' | 'small_molecule' | 'general'

export interface PipelineSceneTab {
  id: PipelineSceneId
  label: string
}

export const PIPELINE_SCENE_TABS: PipelineSceneTab[] = [
  { id: 'all', label: '全部' },
  { id: 'antibody', label: '抗体工程' },
  { id: 'peptide', label: '多肽设计' },
  { id: 'small_molecule', label: '小分子' },
  { id: 'general', label: '通用蛋白' },
]

export interface PipelineStepDef {
  id: string
  label: string
  description: string
  /** 对应原子模块，可单独跳转运行 */
  moduleId?: ModuleId
  moduleRoute?: string
}

export interface PipelineWorkflowDef {
  id: string
  title: string
  description: string
  scene: Exclude<PipelineSceneId, 'all'>
  accent: 'teal' | 'blue' | 'cyan' | 'violet'
  steps: PipelineStepDef[]
  estimatedDuration: string
  /** 占位：流水线编排尚未接入后端 */
  status: 'placeholder' | 'beta'
  /** 详情页统一输入区说明 */
  inputHint: string
  inputFields: { key: string; label: string; placeholder: string; required?: boolean }[]
}

export const PIPELINE_WORKFLOWS: PipelineWorkflowDef[] = [
  {
    id: 'affinity-maturation',
    title: '亲和力成熟',
    description:
      '从 WT 抗体–抗原复合物出发：round1 双轨采样 → Boltz2 全量折叠 → Rosetta 界面能 → 导出 ranked / wetlab。',
    scene: 'antibody',
    accent: 'blue',
    estimatedDuration: '约 2–6 小时（视突变规模与 GPU 负载）',
    status: 'beta',
    inputHint: '提交 FASTA；可选上传复合物 PDB。任务经 Celery 异步执行，产物在 exports/ 目录。',
    inputFields: [
      { key: 'name', label: '任务名称', placeholder: '例如 lycov1404 VHH', required: true },
      { key: 'binder_fasta', label: '抗体/VHH 序列', placeholder: '粘贴 FASTA 或从折叠任务导入', required: true },
      { key: 'antigen_fasta', label: '抗原序列', placeholder: '粘贴抗原 FASTA', required: true },
    ],
    steps: [
      {
        id: 'round1',
        label: 'Round1 双轨采样',
        description: 'ESM / AntiFold 等生成 tier A/B/C 突变候选。',
      },
      {
        id: 'boltz2',
        label: 'Boltz2 全量折叠',
        description: 'WT + 全部候选复合物结构预测（与 fold 共用 GPU）。',
        moduleId: 'fold',
        moduleRoute: '/fold/new',
      },
      {
        id: 'rosetta',
        label: 'Rosetta 界面评价',
        description: 'PyRosetta Relax + InterfaceAnalyzer，计算 ddG / ΔE。',
        moduleId: 'rosetta',
        moduleRoute: '/rosetta/new',
      },
      {
        id: 'export',
        label: '排序与导出',
        description: 'ranked_mutations.csv、wetlab 短名单与 structures/。',
        moduleId: 'affinity_redesign',
        moduleRoute: '/affinity-redesign/new',
      },
    ],
  },
  {
    id: 'peptide-target-design',
    title: '多肽遮蔽设计',
    description:
      '在抗体 paratope 空腔处：RFdiffusion 环肽骨架采样 → 多轮 ProteinMPNN + 环化 FastRelax → 导出设计序列。',
    scene: 'peptide',
    accent: 'teal',
    estimatedDuration: '试跑约 1–4 小时；规模 20k 骨架可达数天',
    status: 'beta',
    inputHint: '上传空 paratope 的抗体单链 PDB，或从 Boltz2 任务抽取 H 链；配置 hotspot 与骨架规模。',
    inputFields: [
      { key: 'name', label: '任务名称', placeholder: '例如 CD98_VHH_mask', required: true },
      { key: 'antibody_pdb', label: '抗体单链 PDB', placeholder: '空 paratope，非复合物', required: true },
      { key: 'hotspot_res', label: 'Hotspot 残基', placeholder: 'H35,H47,H50,H104,H110', required: true },
    ],
    steps: [
      {
        id: 'rfdiffusion',
        label: 'RFdiffusion 骨架',
        description: '在 hotspot 界面采样环肽 backbone，多 GPU 并行。',
      },
      {
        id: 'mpnn',
        label: 'MPNN + FastRelax',
        description: '多轮 ProteinMPNN 序列设计与环化结构松弛。',
        moduleId: 'design',
        moduleRoute: '/design/new',
      },
      {
        id: 'export',
        label: '序列导出',
        description: 'sequences_final.csv、structures/ 与 summary.json。',
        moduleId: 'masking_peptide',
        moduleRoute: '/masking-peptide/new',
      },
    ],
  },
]

export function pipelineById(id: string): PipelineWorkflowDef | undefined {
  return PIPELINE_WORKFLOWS.find((p) => p.id === id)
}

export function pipelinesForScene(scene: PipelineSceneId): PipelineWorkflowDef[] {
  if (scene === 'all') return PIPELINE_WORKFLOWS
  return PIPELINE_WORKFLOWS.filter((p) => p.scene === scene)
}
