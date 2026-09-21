export type ModuleId =
  | 'home'
  | 'antibody_projects'
  | 'fold'
  | 'design'
  | 'rosetta'
  | 'developability'
  | 'maturation'
  | 'affinity_redesign'
  | 'masking_peptide'
  | 'hydro_redesign'
  | 'cic_profile'
  | 'tnp_profile'
  | 'synthesis'
  | 'docking'
  | 'md'

export type ModuleJobKind = Exclude<ModuleId, 'home' | 'fold' | 'antibody_projects'>

export type ModuleIconKey =
  | 'home'
  | 'antibody_projects'
  | 'fold'
  | 'design'
  | 'rosetta'
  | 'developability'
  | 'maturation'
  | 'affinity_redesign'
  | 'masking_peptide'
  | 'hydro_redesign'
  | 'cic_profile'
  | 'tnp_profile'
  | 'synthesis'
  | 'docking'
  | 'md'

export interface ModuleDefinition {
  id: ModuleId
  segment: string
  routePrefix: string
  label: string
  hint: string
  iconKey: ModuleIconKey
  jobKind: ModuleJobKind | null
  routeTitles: {
    module: string
    new: string
    tasks: string
    task: string
  }
  batchRouteName?: string
}

export const MODULE_REGISTRY = [
  {
    id: 'home',
    segment: 'home',
    routePrefix: 'home',
    label: '首页',
    hint: '平台概览与模块入口',
    iconKey: 'home',
    jobKind: null,
    routeTitles: { module: '首页', new: '首页', tasks: '首页', task: '首页' },
  },
  {
    id: 'antibody_projects',
    segment: 'antibody-projects',
    routePrefix: 'antibody-projects',
    label: '抗体改造项目',
    hint: '管理候选抗体、版本谱系与实验记录',
    iconKey: 'antibody_projects',
    jobKind: null,
    routeTitles: {
      module: '抗体改造项目',
      new: '新建项目',
      tasks: '项目列表',
      task: '项目详情',
    },
  },
  {
    id: 'fold',
    segment: 'fold',
    routePrefix: 'fold',
    label: '结构预测',
    hint: 'Boltz2 / ESMFold2 复合物折叠',
    iconKey: 'fold',
    jobKind: null,
    routeTitles: { module: '结构预测', new: '新建预测', tasks: '全部任务', task: '任务详情' },
  },
  {
    id: 'design',
    segment: 'design',
    routePrefix: 'design',
    label: '序列设计',
    hint: 'ProteinMPNN 骨架约束序列设计',
    iconKey: 'design',
    jobKind: 'design',
    routeTitles: { module: '序列设计', new: '新建设计', tasks: '全部任务', task: '设计详情' },
  },
  {
    id: 'rosetta',
    segment: 'rosetta',
    routePrefix: 'rosetta',
    label: '结构评价',
    hint: 'Rosetta Relax 与界面 ΔΔG 排序',
    iconKey: 'rosetta',
    jobKind: 'rosetta',
    routeTitles: { module: '结构评价', new: '新建评价', tasks: '全部任务', task: '评价详情' },
  },
  {
    id: 'developability',
    segment: 'developability',
    routePrefix: 'developability',
    label: '序列改造',
    hint: 'ESM-2 与 MAXWELL 并列打分',
    iconKey: 'developability',
    jobKind: 'developability',
    routeTitles: { module: '序列改造', new: '新建改造', tasks: '全部任务', task: '改造详情' },
  },
  {
    id: 'maturation',
    segment: 'maturation',
    routePrefix: 'maturation',
    label: '亲和力成熟',
    hint: 'IgGM CDR 变体采样',
    iconKey: 'maturation',
    jobKind: 'maturation',
    routeTitles: { module: '亲和力成熟', new: '新建成熟', tasks: '全部任务', task: '成熟详情' },
  },
  {
    id: 'affinity_redesign',
    segment: 'affinity-redesign',
    routePrefix: 'affinity-redesign',
    label: '亲和力改造',
    hint: 'round1 → Boltz2 → Rosetta 端到端流水线',
    iconKey: 'affinity_redesign',
    jobKind: 'affinity_redesign',
    routeTitles: { module: '亲和力改造', new: '新建改造', tasks: '全部任务', task: '改造详情' },
  },
  {
    id: 'masking_peptide',
    segment: 'masking-peptide',
    routePrefix: 'masking-peptide',
    label: '多肽遮蔽设计',
    hint: 'RFdiffusion + MPNN 环肽设计（CD98）',
    iconKey: 'masking_peptide',
    jobKind: 'masking_peptide',
    routeTitles: { module: '多肽遮蔽设计', new: '新建设计', tasks: '全部任务', task: '设计详情' },
  },
  {
    id: 'hydro_redesign',
    segment: 'hydro-redesign',
    routePrefix: 'hydro-redesign',
    label: '疏水性改造',
    hint: '表面疏水斑 × 亲水突变（无抗原）',
    iconKey: 'hydro_redesign',
    jobKind: 'hydro_redesign',
    routeTitles: { module: '疏水性改造', new: '新建改造', tasks: '全部任务', task: '改造详情' },
    batchRouteName: 'hydro-redesign-batch',
  },
  {
    id: 'cic_profile',
    segment: 'cic-profile',
    routePrefix: 'cic-profile',
    label: 'CIC 表面斑',
    hint: '实验 pH 下正电 / 负电 / 疏水斑（诊断）',
    iconKey: 'cic_profile',
    jobKind: 'cic_profile',
    routeTitles: { module: 'CIC 表面斑', new: '新建分析', tasks: '全部任务', task: '分析详情' },
  },
  {
    id: 'tnp_profile',
    segment: 'tnp-profile',
    routePrefix: 'tnp-profile',
    label: 'VHH 可开发性画像',
    hint: 'Boltz2 · Kabat 六项画像',
    iconKey: 'tnp_profile',
    jobKind: 'tnp_profile',
    routeTitles: { module: 'VHH 可开发性画像', new: '新建画像', tasks: '全部任务', task: '画像详情' },
    batchRouteName: 'tnp-profile-batch',
  },
  {
    id: 'synthesis',
    segment: 'synthesis',
    routePrefix: 'synthesis',
    label: '合成候选',
    hint: '测序表与突变表交叉筛选',
    iconKey: 'synthesis',
    jobKind: 'synthesis',
    routeTitles: { module: '合成候选', new: '新建筛选', tasks: '全部任务', task: '筛选结果' },
  },
  {
    id: 'docking',
    segment: 'docking',
    routePrefix: 'docking',
    label: '分子对接',
    hint: '口袋检测引导的盲对接（Vina）',
    iconKey: 'docking',
    jobKind: 'docking',
    routeTitles: { module: '分子对接', new: '新建对接', tasks: '全部任务', task: '对接详情' },
  },
  {
    id: 'md',
    segment: 'md',
    routePrefix: 'md',
    label: 'MD 验证',
    hint: 'GROMACS 显式溶剂模拟',
    iconKey: 'md',
    jobKind: 'md',
    routeTitles: { module: 'MD 验证', new: '新建 MD', tasks: '全部任务', task: 'MD 详情' },
  },
] as const satisfies readonly ModuleDefinition[]

export const MODULE_BY_ID = Object.fromEntries(
  MODULE_REGISTRY.map((module) => [module.id, module]),
) as Record<ModuleId, (typeof MODULE_REGISTRY)[number]>

export const TASK_MODULES = MODULE_REGISTRY.filter(
  (module): module is (typeof MODULE_REGISTRY)[number] & { jobKind: ModuleJobKind } =>
    module.jobKind !== null,
)

export function moduleDefinition(id: ModuleId): ModuleDefinition {
  return MODULE_BY_ID[id]
}

export function moduleDefinitionFromSegment(segment: string): ModuleDefinition | undefined {
  return MODULE_REGISTRY.find((module) => module.segment === segment)
}

export function moduleDefinitionFromPath(path: string): ModuleDefinition {
  if (path === '/' || path.startsWith('/home')) return MODULE_BY_ID.home
  if (path.startsWith('/ras-docking')) return MODULE_BY_ID.docking
  return (
    [...MODULE_REGISTRY]
      .filter((module) => module.id !== 'home')
      .sort((a, b) => b.segment.length - a.segment.length)
      .find((module) => path.startsWith(`/${module.segment}`)) ?? MODULE_BY_ID.home
  )
}
