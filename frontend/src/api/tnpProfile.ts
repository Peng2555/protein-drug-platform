import { api, apiJson } from './client'
import { downloadBlob } from '@/utils/download'
import type {
  Batch,
  BatchDetail,
  BatchJobsListOut,
  BatchListOut,
  TnpProfileJob,
  TnpProfileJobListOut,
  TnpProfileProgressOut,
  TnpProfileRankedOut,
} from './types'

export type TnpProfileCreateBody = {
  name?: string | null
  fasta: string
}

export async function fetchTnpProfileJobs(limit = 50) {
  return apiJson<TnpProfileJobListOut>(`/api/tnp-profile-jobs?limit=${limit}`)
}

export async function fetchTnpProfileBatches(limit = 50) {
  return apiJson<BatchListOut>(`/api/tnp-profile-jobs/batches?limit=${limit}`)
}

export async function fetchTnpProfileBatch(id: string) {
  return apiJson<BatchDetail>(`/api/tnp-profile-jobs/batches/${id}`)
}

export async function fetchTnpProfileBatchJobs(id: string, limit = 200, offset = 0) {
  return apiJson<BatchJobsListOut>(
    `/api/tnp-profile-jobs/batches/${id}/jobs?limit=${limit}&offset=${offset}`,
  )
}

export async function createTnpProfileBatch(body: TnpProfileCreateBody) {
  return apiJson<{ batch: Batch; job_ids: string[] }>('/api/tnp-profile-jobs/batches', {
    method: 'POST',
    data: body,
  })
}

export async function deleteTnpProfileBatch(id: string) {
  await apiJson(`/api/tnp-profile-jobs/batches/${id}`, { method: 'DELETE' })
}

export async function downloadTnpProfileBatchCsv(id: string) {
  const response = await api.get(`/api/tnp-profile-jobs/batches/${id}/export.csv`, {
    responseType: 'blob',
  })
  downloadBlob(response.data, `tnp_batch_${id.slice(0, 8)}.csv`)
}

export async function fetchTnpProfileJob(id: string) {
  return apiJson<TnpProfileJob>(`/api/tnp-profile-jobs/${id}`)
}

export async function fetchTnpProfileProgress(id: string) {
  return apiJson<TnpProfileProgressOut>(`/api/tnp-profile-jobs/${id}/progress`)
}

export async function fetchTnpProfileRanked(id: string) {
  return apiJson<TnpProfileRankedOut>(`/api/tnp-profile-jobs/${id}/ranked`)
}

export async function createTnpProfileJob(body: TnpProfileCreateBody) {
  return apiJson<TnpProfileJob>('/api/tnp-profile-jobs', { method: 'POST', data: body })
}

export async function uploadTnpProfileJob(
  fasta: string,
  structure: File | null,
  body: Pick<TnpProfileCreateBody, 'name'>,
) {
  const fd = new FormData()
  fd.append('fasta', fasta)
  if (body.name) fd.append('name', body.name)
  if (structure) fd.append('structure', structure)
  return apiJson<TnpProfileJob>('/api/tnp-profile-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteTnpProfileJob(id: string) {
  await apiJson(`/api/tnp-profile-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadTnpProfileFile(id: string, filename: string) {
  const response = await api.get(`/api/tnp-profile-jobs/${id}/files/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
  downloadBlob(response.data, filename)
}

export async function fetchTnpProfileCif(id: string): Promise<string | null> {
  try {
    const response = await api.get(`/api/tnp-profile-jobs/${id}/files/pred.cif`, { responseType: 'text' })
    const text = typeof response.data === 'string' ? response.data : String(response.data ?? '')
    return text.includes('data_') || text.includes('_atom_site') ? text : null
  } catch {
    return null
  }
}
