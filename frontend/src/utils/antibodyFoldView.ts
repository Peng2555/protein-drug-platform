import type { AntibodyVersion, VersionChain, VersionMutation } from '@/api/antibodyProjects'
import type { CdrSpan, ChainSequence } from '@/api/types'

export function foldChainId(chainRole: string): string {
  const role = chainRole.trim().toUpperCase()
  if (role === 'VL' || role === 'L' || role === 'LIGHT') return 'L'
  return 'H'
}

export function residueKey(chainId: string, seq: number): string {
  return `${chainId}:${seq}`
}

function parseCdrSpans(raw: VersionChain['annotation_json'] | undefined): CdrSpan[] {
  if (!raw || typeof raw !== 'object') return []
  const spans = (raw as { cdr_spans?: unknown }).cdr_spans
  if (!Array.isArray(spans)) return []
  return spans.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const row = item as Record<string, unknown>
    const name = String(row.name || '')
    const start = Number(row.start)
    const end = Number(row.end)
    if (!name || !Number.isFinite(start) || !Number.isFinite(end)) return []
    return [{
      name,
      start,
      end,
      kabat_range: row.kabat_range ? String(row.kabat_range) : '',
      sequence: row.sequence ? String(row.sequence) : '',
    }]
  })
}

function parseKabatLabels(raw: VersionChain['annotation_json'] | undefined, sequence: string): string[] {
  if (!raw || typeof raw !== 'object') {
    return sequence.split('').map((_, i) => String(i + 1))
  }
  const labels = (raw as { kabat_labels?: unknown }).kabat_labels
  if (!Array.isArray(labels)) return sequence.split('').map((_, i) => String(i + 1))
  return sequence.split('').map((_, i) => String(labels[i] ?? i + 1))
}

export function versionToFoldSequences(version: AntibodyVersion): ChainSequence[] {
  return version.chains.map((chain) => {
    const sequence = chain.variable_sequence || ''
    const labels = parseKabatLabels(chain.annotation_json, sequence)
    return {
      chain_id: foldChainId(chain.chain_role),
      length: sequence.length,
      sequence,
      is_antibody: true,
      domain: chain.chain_role,
      scheme: chain.numbering_scheme || 'kabat',
      cdr_spans: parseCdrSpans(chain.annotation_json),
      residues: sequence.split('').map((aa, i) => ({
        index: i + 1,
        aa,
        kabat: labels[i] || String(i + 1),
      })),
    }
  })
}

export function mutationResidueKeys(mutations: VersionMutation[]): string[] {
  const keys: string[] = []
  for (const item of mutations) {
    if (!item.sequence_position) continue
    keys.push(residueKey(foldChainId(item.chain_role), item.sequence_position))
  }
  return keys
}

/** CDR 顺序位点，叠合时排除，让骨架对齐、差别留在 CDR。 */
export function cdrResidueKeys(version: AntibodyVersion): string[] {
  const keys: string[] = []
  for (const chain of version.chains) {
    const chainId = foldChainId(chain.chain_role)
    for (const span of parseCdrSpans(chain.annotation_json)) {
      for (let i = span.start; i <= span.end; i += 1) {
        keys.push(residueKey(chainId, i + 1))
      }
    }
  }
  return keys
}
