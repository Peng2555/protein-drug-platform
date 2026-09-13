/** CIC 正电 / 负电 / 疏水斑着色。 */

import {
  parsePatchResidueLabels,
  residueKey,
  type HydroPatch,
  type HydroResidue,
} from '@/utils/hydroPatches'

export type CicPatchKind = 'positive' | 'negative' | 'hydrophobic'

const KIND_PALETTE: Record<CicPatchKind, readonly string[]> = {
  positive: ['#e11d48', '#f43f5e', '#fb7185', '#be123c'],
  negative: ['#2563eb', '#3b82f6', '#60a5fa', '#1d4ed8'],
  hydrophobic: ['#d97706', '#f59e0b', '#fbbf24', '#b45309'],
}

function asNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function asId(v: unknown): string | null {
  const s = String(v ?? '').trim()
  if (!s || s === 'None' || s === 'null') return null
  return s
}

function asBool(v: unknown): boolean {
  return v === true || v === 'True' || v === 'true' || v === '1' || v === 1
}

export type CicResidue = HydroResidue & {
  charge: number
  charge_sasa: number
  patch_kind: CicPatchKind | null
  hydro_patch_id: string | null
  charge_patch_id: string | null
  cdr: boolean
}

export function parseCicResidues(rows: Record<string, unknown>[]): CicResidue[] {
  return rows.map((row) => {
    const kindRaw = String(row.patch_kind ?? '').trim()
    const kind = (['positive', 'negative', 'hydrophobic'] as const).includes(kindRaw as CicPatchKind)
      ? (kindRaw as CicPatchKind)
      : null
    return {
      chain: String(row.chain ?? '').trim(),
      position: asNum(row.position),
      aa: String(row.aa ?? ''),
      region: String(row.region || 'FR'),
      rsa: asNum(row.rsa),
      sasa: asNum(row.sasa),
      hydro_sasa: asNum(row.hydro_sasa),
      patch_id: asId(row.patch_id),
      hydrophobic: asBool(row.hydrophobic),
      surface: asBool(row.surface_charge) || asBool(row.surface_hydro),
      charge: asNum(row.charge),
      charge_sasa: asNum(row.charge_sasa),
      patch_kind: kind,
      hydro_patch_id: asId(row.hydro_patch_id),
      charge_patch_id: asId(row.charge_patch_id),
      cdr: asBool(row.cdr) || String(row.region || '').startsWith('CDR'),
    }
  })
}

export function parseCicPatches(rows: Record<string, unknown>[], residues: CicResidue[]): HydroPatch[] {
  const counters: Record<CicPatchKind, number> = { positive: 0, negative: 0, hydrophobic: 0 }
  if (rows.length) {
    return rows.map((row) => {
      const patch_id = String(row.patch_id || '')
      const kind = (String(row.kind || row.patch_kind || 'hydrophobic') as CicPatchKind) || 'hydrophobic'
      const pal = KIND_PALETTE[kind] || KIND_PALETTE.hydrophobic
      const i = counters[kind] ?? 0
      counters[kind] = i + 1
      let labels = parsePatchResidueLabels(row.residues)
      if (!labels.length) {
        labels = residues
          .filter((r) => r.patch_id === patch_id)
          .map((r) => `${r.chain}:${r.aa}${r.position}`)
      }
      return {
        patch_id,
        n_residues: asNum(row.n_residues) || labels.length,
        score: asNum(row.score),
        residues: labels,
        color: pal[i % pal.length],
      }
    })
  }
  const groups = new Map<string, CicResidue[]>()
  for (const r of residues) {
    if (!r.patch_id) continue
    const list = groups.get(r.patch_id) ?? []
    list.push(r)
    groups.set(r.patch_id, list)
  }
  return [...groups.entries()].map(([patch_id, list], i) => {
    const kind = list[0]?.patch_kind || 'hydrophobic'
    const pal = KIND_PALETTE[kind]
    return {
      patch_id,
      n_residues: list.length,
      score: list.reduce((s, r) => s + Math.abs(r.charge_sasa || r.hydro_sasa), 0),
      residues: list.map((r) => `${r.chain}:${r.aa}${r.position}`),
      color: pal[i % pal.length],
    }
  })
}

export function patchKindLabel(kind: string | null | undefined) {
  if (kind === 'positive') return '正电'
  if (kind === 'negative') return '负电'
  if (kind === 'hydrophobic') return '疏水'
  return '—'
}

export { residueKey }
export type { HydroPatch }
