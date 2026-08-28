import { apiJson } from './client'
import type {
  BatchDetail,
  BatchJobsListOut,
  BatchListOut,
  VhhPanelCreateOut,
} from './types'

export async function fetchBatches(limit = 50) {
  return apiJson<BatchListOut>(`/api/batches?limit=${limit}`)
}

export async function fetchBatch(id: string) {
  return apiJson<BatchDetail>(`/api/batches/${id}`)
}

export async function fetchBatchJobs(batchId: string, limit: number, offset: number) {
  return apiJson<BatchJobsListOut>(
    `/api/batches/${batchId}/jobs?limit=${limit}&offset=${offset}`,
  )
}

export async function createVhhPanel(body: {
  batch_name?: string | null
  target: { name: string; chain_id: string; sequence: string }
  heavy_chain_id: string
  heavy_chains: Array<{ id: string; sequence: string }>
  engine: string
  use_msa_server: boolean
  boltz_params?: Record<string, unknown>
  esmfold_params?: Record<string, number>
}) {
  return apiJson<VhhPanelCreateOut>('/api/batches/vhh-panel', { method: 'POST', data: body })
}

export async function deleteBatch(id: string) {
  await apiJson(`/api/batches/${id}`, { method: 'DELETE' })
}

export async function exportBatchCsv(batchId: string, batchName: string) {
  const data = await fetchBatchJobs(batchId, 5000, 0)
  const header = [
    'heavy_chain_id',
    'job_name',
    'status',
    'iptm',
    'pdockq',
    'pdockq2',
    'ptm',
    'complex_plddt',
    'confidence_score',
    'runtime_seconds',
    'job_id',
  ]
  const lines = [header.join(',')]
  for (const j of data.items) {
    lines.push(
      [
        j.heavy_chain_id || '',
        j.name || '',
        j.status,
        j.iptm ?? '',
        j.pdockq ?? '',
        j.pdockq2 ?? '',
        j.ptm ?? '',
        j.complex_plddt ?? '',
        j.confidence_score ?? '',
        j.runtime_seconds ?? '',
        j.id,
      ].join(','),
    )
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${batchName.replace(/[^\w.-]+/g, '_')}_results.csv`
  a.click()
  URL.revokeObjectURL(url)
}
