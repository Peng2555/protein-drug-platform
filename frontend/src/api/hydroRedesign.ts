import { api, apiJson } from './client'
import { downloadBlob } from '@/utils/download'
import type {
  Batch,
  BatchDetail,
  BatchJobsListOut,
  BatchListOut,
  HydroRedesignJob,
  HydroRedesignJobListOut,
  HydroRedesignProgressOut,
  HydroRedesignRankedOut,
} from './types'

export type HydroRedesignCreateBody = {
  name?: string | null
  fasta: string
  allow_cdr?: boolean
  allow_charged?: boolean
}

export async function fetchHydroRedesignJobs(limit = 50) {
  return apiJson<HydroRedesignJobListOut>(`/api/hydro-redesign-jobs?limit=${limit}`)
}

export async function fetchHydroRedesignBatches(limit = 50) {
  return apiJson<BatchListOut>(`/api/hydro-redesign-jobs/batches?limit=${limit}`)
}

export async function fetchHydroRedesignBatch(id: string) {
  return apiJson<BatchDetail>(`/api/hydro-redesign-jobs/batches/${id}`)
}

export async function fetchHydroRedesignBatchJobs(id: string, limit = 200, offset = 0) {
  return apiJson<BatchJobsListOut>(
    `/api/hydro-redesign-jobs/batches/${id}/jobs?limit=${limit}&offset=${offset}`,
  )
}

export async function createHydroRedesignBatch(body: HydroRedesignCreateBody) {
  return apiJson<{ batch: Batch; job_ids: string[] }>('/api/hydro-redesign-jobs/batches', {
    method: 'POST',
    data: body,
  })
}

export async function deleteHydroRedesignBatch(id: string) {
  await apiJson(`/api/hydro-redesign-jobs/batches/${id}`, { method: 'DELETE' })
}

export async function downloadHydroRedesignBatchCsv(id: string) {
  const response = await api.get(`/api/hydro-redesign-jobs/batches/${id}/export.csv`, {
    responseType: 'blob',
  })
  downloadBlob(response.data, `hydro_batch_${id.slice(0, 8)}.csv`)
}

export async function fetchHydroRedesignJob(id: string) {
  return apiJson<HydroRedesignJob>(`/api/hydro-redesign-jobs/${id}`)
}

export async function fetchHydroRedesignProgress(id: string) {
  return apiJson<HydroRedesignProgressOut>(`/api/hydro-redesign-jobs/${id}/progress`)
}

export async function fetchHydroRedesignRanked(id: string) {
  return apiJson<HydroRedesignRankedOut>(`/api/hydro-redesign-jobs/${id}/ranked`)
}

export async function createHydroRedesignJob(body: HydroRedesignCreateBody) {
  return apiJson<HydroRedesignJob>('/api/hydro-redesign-jobs', { method: 'POST', data: body })
}

export async function uploadHydroRedesignJob(
  fasta: string,
  structure: File | null,
  body: Pick<HydroRedesignCreateBody, 'name' | 'allow_cdr' | 'allow_charged'>,
) {
  const fd = new FormData()
  fd.append('fasta', fasta)
  if (body.name) fd.append('name', body.name)
  fd.append('allow_cdr', String(Boolean(body.allow_cdr)))
  fd.append('allow_charged', String(Boolean(body.allow_charged)))
  if (structure) fd.append('structure', structure)
  return apiJson<HydroRedesignJob>('/api/hydro-redesign-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteHydroRedesignJob(id: string) {
  await apiJson(`/api/hydro-redesign-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadHydroRedesignFile(id: string, filename: string) {
  const response = await api.get(
    `/api/hydro-redesign-jobs/${id}/files/${encodeURIComponent(filename)}`,
    { responseType: 'blob' },
  )
  downloadBlob(response.data, filename)
}

export async function fetchHydroRedesignCif(id: string): Promise<string | null> {
  try {
    const response = await api.get(`/api/hydro-redesign-jobs/${id}/files/pred.cif`, {
      responseType: 'text',
    })
    const text = typeof response.data === 'string' ? response.data : String(response.data ?? '')
    return text.includes('data_') || text.includes('_atom_site') ? text : null
  } catch {
    return null
  }
}
