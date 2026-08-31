export type FeatureTabId = 'antibody' | 'peptide' | 'enzyme' | 'small_molecule'

export interface FeatureBullet {
  /** 整句文案；**加粗** 片段用 ** 包裹 */
  text: string
}

export interface FeatureTab {
  id: FeatureTabId
  label: string
  title: string
  bullets: FeatureBullet[]
  image: string
  imageAlt: string
  ctaLabel: string
  ctaRoute: string
}

export const FEATURE_TABS: FeatureTab[] = [
  {
    id: 'antibody',
    label: '抗体',
    title: '设计并优化纳米抗体、抗体与复合物',
    bullets: [
      { text: 'Boltz2 / ESMFold2 **批量预测**抗体–抗原复合物结构' },
      { text: 'PyRosetta 约束 Relax + 界面 **ΔΔG** 突变体排序' },
      { text: 'IgGM **亲和力成熟**，CDR 变体采样与筛选' },
      { text: 'ProteinMPNN **界面序列设计**，固定骨架优化序列' },
      { text: 'ESM-2 可开发性打分，辅助 **热稳定性与溶解度** 评估' },
    ],
    image: '/assets/hero/antibody-engineering.png',
    imageAlt: '抗体 Fab 结合靶蛋白结构示意',
    ctaLabel: '进入工作流',
    ctaRoute: '/workflows?scene=antibody',
  },
  {
    id: 'peptide',
    label: '多肽',
    title: '多肽设计与靶点结合分析',
    bullets: [
      { text: '多肽–蛋白 **复合物结构预测**，评估结合构象' },
      { text: '针对 GLP-1、免疫表位等靶点的 **肽段建模**' },
      { text: 'ProteinMPNN **序列设计**与再折叠验证闭环' },
      { text: 'Rosetta **界面能**对比 WT 与突变肽' },
      { text: '批量任务队列，**内网 GPU** 自动调度' },
    ],
    image: '/assets/hero/peptide-design.png',
    imageAlt: '多肽结合抗体 Fab 结构示意',
    ctaLabel: '开始多肽遮蔽设计',
    ctaRoute: '/masking-peptide/new',
  },
  {
    id: 'enzyme',
    label: '酶',
    title: '工业酶与通用蛋白结构计算',
    bullets: [
      { text: '单链与 **多亚基复合物** 高精度结构预测' },
      { text: 'pLDDT / ipTM **置信度** 评估与结构质检' },
      { text: 'ProteinMPNN **活性位点** 周边序列设计' },
      { text: 'Rosetta Relax 能量最小化与 **突变体对比**' },
      { text: 'Mol* 3D 查看器，**pLDDT 着色** 与导出' },
    ],
    image: '/assets/hero/antibody-igg1.png',
    imageAlt: 'IgG1 蛋白三维结构示意',
    ctaLabel: '了解更多',
    ctaRoute: '/fold/new',
  },
  {
    id: 'small_molecule',
    label: '小分子',
    title: '小分子对接与 MD 稳定性验证',
    bullets: [
      { text: '自动 **口袋检测** + AutoDock Vina 盲对接' },
      { text: '结合模式 **可视化** 与打分排序' },
      { text: 'Imatinib 类 **激酶抑制剂** 结合模式分析' },
      { text: 'GROMACS **显式溶剂 MD**，复核结合稳定性' },
      { text: '从对接到 MD 的 **一站式** 内网流水线' },
    ],
    image: '/assets/hero/small-molecule-discovery.png',
    imageAlt: '小分子抑制剂结合激酶结构示意',
    ctaLabel: '了解更多',
    ctaRoute: '/docking/new',
  },
]

/** 将 **text** 转为 HTML 加粗片段（仅用于受控文案） */
export function formatFeatureBullet(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}
