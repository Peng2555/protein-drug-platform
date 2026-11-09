import { api, apiJson } from './client'
import { downloadBlob } from '@/utils/download'
import type {
  AntibodyRowPayload,
  BatchDetail,
  BatchJobsListOut,
  BatchListOut,
  Job,
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

export async function createAntibodyOnly(body: {
  batch_name?: string | null
  heavy_chain_id?: string
  light_chain_id?: string
  antibodies: AntibodyRowPayload[]
  engine: string
  use_msa_server: boolean
  boltz_params?: Record<string, unknown>
  esmfold_params?: Record<string, number>
}) {
  return apiJson<VhhPanelCreateOut>('/api/batches/antibody-only', { method: 'POST', data: body })
}

export async function deleteBatch(id: string) {
  await apiJson(`/api/batches/${id}`, { method: 'DELETE' })
}

/** 与批次任务接口 Query(le=500) 一致；一次请求更大的 limit 会被 422 拒绝。 */
const EXPORT_JOBS_PAGE = 500

function csvCell(value: string | number | null | undefined): string {
  const text = value == null ? '' : String(value)
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`
  return text
}

export async function exportBatchCsv(batchId: string, batchName: string) {
  const items: Job[] = []
  let offset = 0
  let total = Number.POSITIVE_INFINITY
  while (offset < total) {
    const data = await fetchBatchJobs(batchId, EXPORT_JOBS_PAGE, offset)
    total = data.total
    items.push(...data.items)
    if (!data.items.length) break
    offset += data.items.length
  }
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
  for (const j of items) {
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
      ]
        .map(csvCell)
        .join(','),
    )
  }
  const blob = new Blob([`\uFEFF${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  downloadBlob(blob, `${batchName.replace(/[^\w.-]+/g, '_')}_results.csv`)
}

export async function downloadBatchStructures(batchId: string, batchName: string) {
  const resp = await api.get<Blob>(`/api/batches/${batchId}/structures.zip`, {
    responseType: 'blob',
    timeout: 600_000,
  })
  downloadBlob(resp.data, `${batchName.replace(/[^\w.-]+/g, '_')}_structures.zip`)
}
