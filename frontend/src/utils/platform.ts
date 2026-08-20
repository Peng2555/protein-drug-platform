export const PLATFORM_NAME = '蛋白质-药物计算平台'
export const PLATFORM_NAME_EN = 'Protein–Drug Computing Platform'
export const PLATFORM_ORG = '百奥赛图 Biocytogen'
export const PLATFORM_TAGLINE = '从靶点到治疗药物 · Your Partner from Targets to Therapeutics'

export type ModuleId =
  | 'home'
  | 'fold'
  | 'design'
  | 'developability'
  | 'maturation'
  | 'synthesis'
  | 'docking'
  | 'md'

export interface NavItem {
  id: ModuleId
  path: string
  label: string
  hint: string
}

export interface NavGroup {
  id: string
  label: string
  items: NavItem[]
}

export const HOME_NAV: NavItem = {
  id: 'home',
  path: '/home',
  label: '首页',
  hint: '平台概览与模块入口',
}

/** 侧栏分组对齐专业计算平台导航结构。 */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'workbench',
    label: '工作台',
    items: [HOME_NAV],
  },
  {
    id: 'structure',
    label: '结构计算',
    items: [
      { id: 'fold', path: '/fold', label: '结构预测', hint: 'Boltz2 / ESMFold2 复合物折叠' },
    ],
  },
  {
    id: 'sequence',
    label: '序列与抗体',
    items: [
      { id: 'design', path: '/design', label: '序列设计', hint: 'ProteinMPNN 骨架约束序列设计' },
      { id: 'developability', path: '/developability', label: '序列改造', hint: 'ESM-2 与 MAXWELL 并列打分' },
      { id: 'maturation', path: '/maturation', label: '亲和力成熟', hint: 'IgGM CDR 变体采样' },
      { id: 'synthesis', path: '/synthesis', label: '合成候选', hint: '测序表与突变表交叉筛选' },
    ],
  },
  {
    id: 'ligand',
    label: '小分子药物筛选',
    items: [
      { id: 'docking', path: '/docking', label: '分子对接', hint: '口袋检测引导的盲对接（Vina）' },
      { id: 'md', path: '/md', label: 'MD 验证', hint: 'GROMACS 显式溶剂模拟' },
    ],
  },
]

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

export function moduleIdFromPath(path: string): ModuleId {
  if (path === '/' || path.startsWith('/home')) return 'home'
  if (path.startsWith('/md')) return 'md'
  if (path.startsWith('/maturation')) return 'maturation'
  if (path.startsWith('/synthesis')) return 'synthesis'
  if (path.startsWith('/design')) return 'design'
  if (path.startsWith('/developability')) return 'developability'
  if (path.startsWith('/docking') || path.startsWith('/ras-docking')) return 'docking'
  if (path.startsWith('/fold')) return 'fold'
  return 'home'
}

export function navItemById(id: ModuleId): NavItem {
  return ALL_NAV_ITEMS.find((item) => item.id === id) ?? HOME_NAV
}
