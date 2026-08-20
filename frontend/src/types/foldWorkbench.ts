export type FoldMetricTone = 'primary' | 'ok' | 'warn' | 'info' | 'muted'

export interface FoldScoreCard {
  key: string
  label: string
  value: string
  hint: string
  tone: FoldMetricTone
  level?: 'high' | 'mid' | 'low' | null
}

export interface FoldComplexInfo {
  antibodyChains: string
  antigenChains: string
  ligand: string
  totalResidues: number | null
  model: string
  predictedAt: string
}

export interface FoldInterfaceSummary {
  interfaceResidues: number
  hbonds: number
  saltBridges: number
  hydrophobic: number
  pi: number
  qualityHint: string
  qualityTier: 'high' | 'mid' | 'low'
}

export function metricLevel(value: number | null | undefined, kind: 'iptm' | 'plddt' | 'pdockq'): 'high' | 'mid' | 'low' | null {
  if (value == null || Number.isNaN(value)) return null
  if (kind === 'iptm') {
    if (value >= 0.8) return 'high'
    if (value >= 0.5) return 'mid'
    return 'low'
  }
  if (kind === 'plddt') {
    const v = value <= 1.5 ? value * 100 : value
    if (v >= 90) return 'high'
    if (v >= 70) return 'mid'
    return 'low'
  }
  if (value >= 0.49) return 'high'
  if (value >= 0.23) return 'mid'
  return 'low'
}

export function levelLabel(level: 'high' | 'mid' | 'low' | null | undefined): string {
  if (level === 'high') return '高'
  if (level === 'mid') return '中'
  if (level === 'low') return '低'
  return '—'
}
