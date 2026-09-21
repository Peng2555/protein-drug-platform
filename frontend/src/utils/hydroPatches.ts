/** 疏水斑可视化：颜色、残基解析、与 3D 着色共用。 */

export const HYDRO_PATCH_PALETTE = [
  '#e11d48',
  '#f97316',
  '#ca8a04',
  '#16a34a',
  '#0891b2',
  '#2563eb',
  '#7c3aed',
  '#db2777',
  '#65a30d',
  '#0d9488',
  '#ea580c',
  '#4f46e5',
] as const

export type HydroResidue = {
  chain: string
  position: number
  aa: string
  region: string
  rsa: number
  sasa: number
  sap: number
  sap_std: number
  hydro_sasa: number
  patch_id: string | null
  hydrophobic: boolean
  surface: boolean
}

export type HydroPatch = {
  patch_id: string
  n_residues: number
  score: number
  residues: string[]
  color: string
}

function asBool(v: unknown): boolean {
  return v === true || v === 'True' || v === 'true' || v === '1' || v === 1
}

function asNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function residueKey(chain: string, position: number): string {
  return `${chain}:${position}`
}

export function parsePatchResidueLabels(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(String).map((s) => s.trim()).filter(Boolean)
  const s = String(raw ?? '').trim()
  if (!s) return []
  if (s.includes(';')) return s.split(';').map((x) => x.trim()).filter(Boolean)
  return s
    .replace(/[\[\]'"]/g, '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
}

export function parseHydroResidues(rows: Record<string, unknown>[]): HydroResidue[] {
  return rows.map((row) => {
    const chain = String(row.chain ?? '').trim()
    const position = asNum(row.position)
    const patchRaw = String(row.patch_id ?? '').trim()
    return {
      chain,
      position,
      aa: String(row.aa ?? ''),
      region: String(row.region || 'FR'),
      rsa: asNum(row.rsa),
      sasa: asNum(row.sasa),
      sap: asNum(row.sap ?? row.hydro_sasa),
      sap_std: asNum(row.sap_std),
      hydro_sasa: asNum(row.hydro_sasa ?? row.sap),
      patch_id: patchRaw && patchRaw !== 'None' && patchRaw !== 'null' ? patchRaw : null,
      hydrophobic: asBool(row.hydrophobic),
      surface: asBool(row.surface),
    }
  })
}

export function parseHydroPatches(
  rows: Record<string, unknown>[],
  residues: HydroResidue[],
): HydroPatch[] {
  if (rows.length) {
    return rows.map((row, i) => {
      const patch_id = String(row.patch_id || `P${i + 1}`)
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
        color: HYDRO_PATCH_PALETTE[i % HYDRO_PATCH_PALETTE.length],
      }
    })
  }
  const groups = new Map<string, HydroResidue[]>()
  for (const r of residues) {
    if (!r.patch_id) continue
    const list = groups.get(r.patch_id) ?? []
    list.push(r)
    groups.set(r.patch_id, list)
  }
  return [...groups.entries()].map(([patch_id, list], i) => ({
    patch_id,
    n_residues: list.length,
    score: list.reduce((s, r) => s + (r.sap || r.hydro_sasa), 0),
    residues: list.map((r) => `${r.chain}:${r.aa}${r.position}`),
    color: HYDRO_PATCH_PALETTE[i % HYDRO_PATCH_PALETTE.length],
  }))
}

export function hydroColorByResidue(
  residues: HydroResidue[],
  patches: HydroPatch[],
): Map<string, string> {
  const colorOf = new Map(patches.map((p) => [p.patch_id, p.color]))
  const out = new Map<string, string>()
  for (const r of residues) {
    if (!r.patch_id) continue
    const color = colorOf.get(r.patch_id)
    if (!color) continue
    out.set(residueKey(r.chain, r.position), color)
  }
  return out
}

export function patchResidueItems(
  patch: HydroPatch | undefined,
  residues: HydroResidue[],
): Array<{ chain_id: string; seq_num: number }> {
  if (!patch) return []
  const fromRows = residues
    .filter((r) => r.patch_id === patch.patch_id)
    .map((r) => ({ chain_id: r.chain, seq_num: r.position }))
  if (fromRows.length) return fromRows
  return patch.residues
    .map((label) => {
      const m = label.match(/^([A-Za-z0-9]+):[A-Z](\d+)$/) || label.match(/^([A-Za-z0-9]+)(\d+)$/)
      if (!m) return null
      return { chain_id: m[1], seq_num: Number(m[2]) }
    })
    .filter((x): x is { chain_id: string; seq_num: number } => !!x)
}
