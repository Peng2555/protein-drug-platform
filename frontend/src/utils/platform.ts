import {
  MODULE_BY_ID,
  moduleDefinition,
  moduleDefinitionFromPath,
  type ModuleId,
} from '@/config/moduleRegistry'

export const PLATFORM_NAME = '蛋白质-药物计算平台'
export const PLATFORM_NAME_EN = 'Protein–Drug Computing Platform'
export const PLATFORM_ORG = '百奥赛图 Biocytogen'
export const PLATFORM_TAGLINE = '从靶点到治疗药物 · Your Partner from Targets to Therapeutics'

export type { ModuleId } from '@/config/moduleRegistry'

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
  id: MODULE_BY_ID.home.id,
  path: `/${MODULE_BY_ID.home.segment}`,
  label: MODULE_BY_ID.home.label,
  hint: MODULE_BY_ID.home.hint,
}

function navItem(id: ModuleId): NavItem {
  const module = moduleDefinition(id)
  return { id, path: `/${module.segment}`, label: module.label, hint: module.hint }
}

/** 侧栏分组对齐专业计算平台导航结构。 */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'workbench',
    label: '工作台',
    items: [HOME_NAV],
  },
  {
    id: 'research',
    label: '研发项目',
    items: [navItem('antibody_projects')],
  },
  {
    id: 'structure',
    label: '结构计算',
    items: [navItem('fold')],
  },
  {
    id: 'sequence',
    label: '序列与抗体',
    items: [
      navItem('design'),
      navItem('rosetta'),
      navItem('developability'),
      navItem('maturation'),
      navItem('affinity_redesign'),
      navItem('masking_peptide'),
      navItem('hydro_redesign'),
      navItem('cic_profile'),
      navItem('tnp_profile'),
      navItem('synthesis'),
    ],
  },
  {
    id: 'ligand',
    label: '小分子药物筛选',
    items: [
      navItem('docking'),
      navItem('md'),
    ],
  },
]

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

export function moduleIdFromPath(path: string): ModuleId {
  return moduleDefinitionFromPath(path).id
}

/** Vue Router 路由名前缀（与 moduleChildren 的 path 一致） */
export function moduleRoutePrefix(id: ModuleId): string {
  return moduleDefinition(id).routePrefix
}

export function moduleNewRouteName(id: ModuleId): string {
  return `${moduleRoutePrefix(id)}-new`
}

export function navItemById(id: ModuleId): NavItem {
  return ALL_NAV_ITEMS.find((item) => item.id === id) ?? HOME_NAV
}
