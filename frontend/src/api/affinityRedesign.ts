import { api, apiJson } from './client'
import type {
  AffinityRedesignJob,
  AffinityRedesignJobListOut,
  AffinityRedesignProgressOut,
  AffinityRedesignRankedOut,
} from './types'

export type AffinityRedesignCreateBody = {
  name?: string | null
  fasta: string
  skip_round1?: boolean
}

export async function fetchAffinityRedesignJobs(limit = 50) {
  return apiJson<AffinityRedesignJobListOut>(`/api/affinity-redesign-jobs?limit=${limit}`)
}

export async function fetchAffinityRedesignJob(id: string) {
  return apiJson<AffinityRedesignJob>(`/api/affinity-redesign-jobs/${id}`)
}

export async function fetchAffinityRedesignRanked(id: string) {
  return apiJson<AffinityRedesignRankedOut>(`/api/affinity-redesign-jobs/${id}/ranked`)
}

export async function fetchAffinityRedesignProgress(id: string) {
  return apiJson<AffinityRedesignProgressOut>(`/api/affinity-redesign-jobs/${id}/progress`)
}

export async function createAffinityRedesignJob(body: AffinityRedesignCreateBody) {
  return apiJson<AffinityRedesignJob>('/api/affinity-redesign-jobs', { method: 'POST', data: body })
}

export async function uploadAffinityRedesignJob(
  fasta: string,
  complexPdb: File | null,
  body: Pick<AffinityRedesignCreateBody, 'name' | 'skip_round1'>,
) {
  const fd = new FormData()
  fd.append('fasta', fasta)
  if (body.name) fd.append('name', body.name)
  fd.append('skip_round1', String(Boolean(body.skip_round1)))
  if (complexPdb) fd.append('complex_pdb', complexPdb)
  return apiJson<AffinityRedesignJob>('/api/affinity-redesign-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteAffinityRedesignJob(id: string) {
  await apiJson(`/api/affinity-redesign-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadAffinityRedesignFile(id: string, filename: string) {
  const response = await api.get(
    `/api/affinity-redesign-jobs/${id}/files/${encodeURIComponent(filename)}`,
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
    anchor.remove()
  }, 1000)
}
