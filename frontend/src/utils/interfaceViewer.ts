import type {
  InterfaceChainMeta,
  InterfaceInteraction,
  InterfacePair,
  JobInterfaceData,
  Mol3DViewer,
} from '@/types/structure'
import { cartoonStyle, hexColorToInt } from '@/composables/use3Dmol'

export const IX_TYPE_LABELS: Record<string, string> = {
  hbond: '氢键',
  salt_bridge: '盐桥',
  hydrophobic: '疏水',
  pi_stacking: 'π-堆积',
  pi_cation: 'π-阳离子',
  water_bridge: '水桥',
}

/** Draw in 3D; hydrophobic contacts omitted to avoid dense line mesh. */
export const IX_DRAW_IN_3D = new Set(['hbond', 'salt_bridge', 'pi_stacking', 'pi_cation', 'water_bridge'])

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
  hbond: 0.035,
  salt_bridge: 0.085,
  hydrophobic: 0.025,
  pi_stacking: 0.055,
  pi_cation: 0.055,
  water_bridge: 0.04,
}

export const IFACE_CHAIN_PALETTE = {
  target: 0x5b8def,
  binder: 0xe07a5f,
} as const

export function hexCssFromInt(colorInt: number): string {
  return `#${colorInt.toString(16).padStart(6, '0')}`
}

export function getInterfaceChainPalette(
  primary: InterfacePair,
  chains?: InterfaceChainMeta[] | null,
): Record<string, number> {
  const meta = Object.fromEntries((chains || []).map((c) => [c.chain_id, c]))
  const palette: Record<string, number> = {}
  for (const cid of [primary.chain_a, primary.chain_b]) {
    const m = meta[cid] || {}
    const isTarget =
      m.role === 'target' ||
      (m.label != null && /靶|抗原|target/i.test(m.label)) ||
      cid === 'A'
    palette[cid] = isTarget ? IFACE_CHAIN_PALETTE.target : IFACE_CHAIN_PALETTE.binder
  }
  return palette
}

export function collectInterfaceResidueKeys(primary: InterfacePair): {
  interactions: InterfaceInteraction[]
  ixResKeys: Set<string>
} {
  const interactions = (primary.interactions || []).filter((ix) => ix.type !== 'contact')
  const ixResKeys = new Set<string>()
  for (const ix of interactions) {
    ixResKeys.add(`${ix.chain_a}:${ix.resnum_a}`)
    ixResKeys.add(`${ix.chain_b}:${ix.resnum_b}`)
  }
  return { interactions, ixResKeys }
}

export function drawInterfaceInteractionGraphics(
  viewer: Mol3DViewer,
  interactions: InterfaceInteraction[],
): void {
  for (const ix of interactions) {
    if (!IX_DRAW_IN_3D.has(ix.type)) continue
    if (!ix.coord_a?.length || !ix.coord_b?.length) continue
    const color = IX_COLORS[ix.type] || 0x64748b
    const radius = IX_LINE_RADIUS[ix.type] || 0.04
    const start = { x: ix.coord_a[0], y: ix.coord_a[1], z: ix.coord_a[2] }
    const end = { x: ix.coord_b[0], y: ix.coord_b[1], z: ix.coord_b[2] }
    viewer.addCylinder({ start, end, radius, color, fromCap: 1, toCap: 1 })
    if (ix.type === 'hbond' || ix.type === 'salt_bridge') {
      viewer.addSphere({
        center: start,
        radius: ix.type === 'salt_bridge' ? 0.18 : 0.12,
        color,
      })
      viewer.addSphere({
        center: end,
        radius: ix.type === 'salt_bridge' ? 0.18 : 0.12,
        color,
      })
    }
  }
}

export function paintInterfaceViewer(
  viewer: Mol3DViewer,
  primary: InterfacePair,
  chains?: InterfaceChainMeta[] | null,
): Array<{ chain: string; resi: number }> {
  const palette = getInterfaceChainPalette(primary, chains)
  const { interactions, ixResKeys } = collectInterfaceResidueKeys(primary)
  const ifaceRes = [...(primary.residues_a || []), ...(primary.residues_b || [])]
  const ifaceKeys = new Set(ifaceRes.map((r) => `${r.chain_id}:${r.seq_num}`))

  for (const ch of chains || []) {
    const onIface = ch.chain_id === primary.chain_a || ch.chain_id === primary.chain_b
    if (!onIface) {
      viewer.setStyle({ chain: ch.chain_id }, { cartoon: cartoonStyle({ opacity: 0 }) })
      continue
    }
    const baseColor = palette[ch.chain_id] || hexColorToInt(ch.color)
    viewer.setStyle({ chain: ch.chain_id }, {
      cartoon: cartoonStyle({ color: baseColor, opacity: 0.22, thickness: 0.28, width: 0.9 }),
    })
  }

  for (const r of ifaceRes) {
    const key = `${r.chain_id}:${r.seq_num}`
    const baseColor = palette[r.chain_id] || IFACE_CHAIN_PALETTE.target
    const inIx = ixResKeys.has(key)
    viewer.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
      cartoon: cartoonStyle({
        color: baseColor,
        opacity: inIx ? 1 : 0.82,
        thickness: inIx ? 0.52 : 0.4,
        width: inIx ? 1.45 : 1.15,
      }),
    })
    if (inIx) {
      viewer.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
        stick: { colorscheme: 'greenCarbon', radius: 0.11, opacity: 0.88 },
      })
    }
  }

  drawInterfaceInteractionGraphics(viewer, interactions)

  const focusSelections: Array<{ chain: string; resi: number }> = []
  for (const key of ixResKeys.size ? ixResKeys : ifaceKeys) {
    const [chain, resi] = key.split(':')
    focusSelections.push({ chain, resi: parseInt(resi, 10) })
  }
  return focusSelections
}

export interface InterfaceOverlayRow {
  kind: 'chain' | 'interaction'
  label: string
  color: string
  line?: boolean
}

export function buildInterfaceViewerOverlayRows(
  data: JobInterfaceData,
  primary: InterfacePair,
): { chainRows: InterfaceOverlayRow[]; ixRows: InterfaceOverlayRow[]; hasHydrophobic: boolean } {
  const palette = getInterfaceChainPalette(primary, data.chains)
  const chainRows: InterfaceOverlayRow[] = [
    {
      kind: 'chain',
      label: `${primary.label_a || primary.chain_a} · 链 ${primary.chain_a}`,
      color: hexCssFromInt(palette[primary.chain_a]),
    },
    {
      kind: 'chain',
      label: `${primary.label_b || primary.chain_b} · 链 ${primary.chain_b}`,
      color: hexCssFromInt(palette[primary.chain_b]),
    },
  ]
  const presentIx = new Set((primary.interactions || []).map((ix) => ix.type))
  const ixRows = Object.entries(IX_TYPE_LABELS)
    .filter(([k]) => presentIx.has(k) && IX_DRAW_IN_3D.has(k))
    .map(([k, lbl]) => ({
      kind: 'interaction' as const,
      label: lbl,
      color: IX_LINE_CSS[k],
      line: true,
    }))
  return { chainRows, ixRows, hasHydrophobic: presentIx.has('hydrophobic') }
}
