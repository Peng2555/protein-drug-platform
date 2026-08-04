/** Shared types for 3D structure & PLIP interface visualization (mirrors backend schemas). */

export type ViewerColorMode = 'chain' | 'plddt'

export interface SelectedResidue {
  chainId: string
  resi: number
}

export interface InterfaceChainMeta {
  chain_id: string
  length: number
  label: string
  role: string
  color: string
  is_antibody?: boolean
}

export interface InterfaceResidue {
  chain_id: string
  seq_num: number
  resname: string
}

export interface InterfaceInteraction {
  type: string
  chain_a: string
  resnum_a: number
  resname_a: string
  atom_a: string
  chain_b: string
  resnum_b: number
  resname_b: string
  atom_b: string
  distance_angstrom: number
  coord_a: number[]
  coord_b: number[]
  detail?: string
}

export interface InterfaceInteractionSummary {
  n_hbonds?: number
  n_salt_bridges?: number
  n_hydrophobic?: number
  n_polar_contacts?: number
  n_contacts?: number
  n_total?: number
  n_pi_stacking?: number
  n_water_bridges?: number
  n_interface_residues_a?: number
  n_interface_residues_b?: number
}

export interface InterfacePair {
  chain_a: string
  chain_b: string
  label_a?: string | null
  label_b?: string | null
  contact_pairs: number
  avg_interface_plddt?: number | null
  avg_interface_pae?: number | null
  pdockq: number
  pdockq2: number
  residues_a: InterfaceResidue[]
  residues_b: InterfaceResidue[]
  interactions?: InterfaceInteraction[]
  interaction_summary?: InterfaceInteractionSummary | null
}

export interface InterfaceReferenceTool {
  name: string
  role: string
  url: string
}

export interface JobInterfaceData {
  job_id: string
  error?: string | null
  contact_cutoff_angstrom?: number
  method?: string | null
  reference_tools?: InterfaceReferenceTool[]
  chains?: InterfaceChainMeta[]
  interfaces?: InterfacePair[]
  primary_interface?: InterfacePair | null
}

export type InteractionFilter = 'all' | string

export interface Mol3DAtom {
  resi?: number
  chain?: string
  b?: number
}

export interface Mol3DSelection {
  chain?: string
  resi?: number
  or?: Array<{ chain: string; resi: number }>
}

export interface Mol3DCartoonStyle {
  color?: number
  colorfunc?: (atom: Mol3DAtom) => number
  opacity?: number
  thickness?: number
}

export interface Mol3DStickStyle {
  colorscheme?: string
  radius?: number
  opacity?: number
}

export interface Mol3DSphereStyle {
  radius?: number
  color?: number
}

export interface Mol3DCylinderSpec {
  start: { x: number; y: number; z: number }
  end: { x: number; y: number; z: number }
  radius: number
  color: number
  fromCap?: number
  toCap?: number
}

export interface Mol3DSphereSpec {
  center: { x: number; y: number; z: number }
  radius: number
  color: number
}

export interface Mol3DViewer {
  addModel: (data: string, format: string) => void
  setStyle: (sel: Mol3DSelection | Record<string, unknown>, style: Record<string, unknown>) => void
  addStyle: (sel: Mol3DSelection | Record<string, unknown>, style: Record<string, unknown>) => void
  removeAllLabels: () => void
  setClickable: (
    sel: Record<string, unknown>,
    flag: boolean,
    callback: (atom: Mol3DAtom, viewer: Mol3DViewer, event: MouseEvent) => void,
  ) => void
  addCylinder: (spec: Mol3DCylinderSpec) => void
  addSphere: (spec: Mol3DSphereSpec) => void
  zoomTo: (sel?: Mol3DSelection | Record<string, unknown>) => void
  zoom: (factor: number) => void
  render: () => void
  clear?: () => void
}

export interface Mol3DGlobal {
  createViewer: (element: HTMLElement, options?: { backgroundColor?: string }) => Mol3DViewer
}

/** PLIP interaction type labels (legacy app.js IX_TYPE_LABELS). */
export const IX_TYPE_LABELS: Record<string, string> = {
  hbond: '氢键',
  salt_bridge: '盐桥',
  hydrophobic: '疏水',
  pi_stacking: 'π-堆积',
  pi_cation: 'π-阳离子',
  water_bridge: '水桥',
}

/** Draw in 3D: only well-defined point-to-point interactions (PLIP atom coords). */
export const IX_DRAW_IN_3D = new Set(['hbond', 'salt_bridge'])

export const IX_COLORS: Record<string, number> = {
  hbond: 0xf59e0b,
  salt_bridge: 0xef4444,
  hydrophobic: 0x94a3b8,
  pi_stacking: 0x8b5cf6,
  pi_cation: 0x06b6d4,
  water_bridge: 0x38bdf8,
}

export const IX_LINE_CSS: Record<string, string> = {
  hbond: '#f59e0b',
  salt_bridge: '#ef4444',
  hydrophobic: '#94a3b8',
  pi_stacking: '#8b5cf6',
  pi_cation: '#06b6d4',
  water_bridge: '#38bdf8',
}

export const IX_LINE_RADIUS: Record<string, number> = {
  hbond: 0.02,
  salt_bridge: 0.028,
  hydrophobic: 0.02,
  pi_stacking: 0.025,
  pi_cation: 0.025,
  water_bridge: 0.022,
}

export const IFACE_CHAIN_PALETTE = {
  target: 0x5b8def,
  binder: 0xe07a5f,
} as const

declare global {
  interface Window {
    $3Dmol?: Mol3DGlobal
  }
}
