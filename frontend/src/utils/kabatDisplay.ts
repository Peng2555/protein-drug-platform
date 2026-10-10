import type { ChainSequence } from '@/api/types'

/** 序列展示用 Kabat 标签；缺编号时回退到顺序位。 */

export function residueKabatLabel(residue: {
  kabat?: string | number | null
  index?: number
  pos?: number
}): string {
  const kabat = residue.kabat
  if (kabat != null && String(kabat).trim() !== '') return String(kabat).trim()
  if (residue.index != null) return String(residue.index)
  if (residue.pos != null) return String(residue.pos)
  return ''
}

export function kabatForPosition(
  chains: ChainSequence[],
  chainId: string,
  position: number,
): string {
  const chain = chains.find((item) => item.chain_id === chainId)
  const hit = chain?.residues?.find((item) => item.index === position)
  const label = hit?.kabat != null ? String(hit.kabat).trim() : ''
  return label || String(position)
}

export function formatAaKabat(
  chains: ChainSequence[],
  chainId: string,
  aa: string,
  position: number,
  kabat?: string | number | null,
): string {
  const number = kabat != null && String(kabat).trim() !== ''
    ? String(kabat).trim()
    : kabatForPosition(chains, chainId, position)
  return `${aa}${number}`
}

export function kabatRangeLabel(
  residues: Array<{ kabat?: string | number | null; index?: number }>,
): string {
  if (!residues.length) return ''
  const first = residueKabatLabel(residues[0])
  const last = residueKabatLabel(residues[residues.length - 1])
  if (!first || !last) return ''
  return first === last ? first : `${first}–${last}`
}
