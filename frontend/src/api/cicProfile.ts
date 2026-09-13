import { api, apiJson } from './client'
import type { CicProfileJob, CicProfileJobListOut, CicProfileProgressOut, CicProfileRankedOut } from './types'

export type CicProfileCreateBody = {
  name?: string | null
  fasta: string
  ph?: number
}

export async function fetchCicProfileJobs(limit = 50) {
  return apiJson<CicProfileJobListOut>(`/api/cic-profile-jobs?limit=${limit}`)
}

export async function fetchCicProfileJob(id: string) {
  return apiJson<CicProfileJob>(`/api/cic-profile-jobs/${id}`)
}

export async function fetchCicProfileProgress(id: string) {
  return apiJson<CicProfileProgressOut>(`/api/cic-profile-jobs/${id}/progress`)
}

export async function fetchCicProfileRanked(id: string) {
  return apiJson<CicProfileRankedOut>(`/api/cic-profile-jobs/${id}/ranked`)
}

export async function createCicProfileJob(body: CicProfileCreateBody) {
  return apiJson<CicProfileJob>('/api/cic-profile-jobs', { method: 'POST', data: body })
}

export async function uploadCicProfileJob(
  fasta: string,
  structure: File | null,
  body: Pick<CicProfileCreateBody, 'name' | 'ph'>,
) {
  const fd = new FormData()
  fd.append('fasta', fasta)
  if (body.name) fd.append('name', body.name)
  fd.append('ph', String(body.ph ?? 7))
  if (structure) fd.append('structure', structure)
  return apiJson<CicProfileJob>('/api/cic-profile-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteCicProfileJob(id: string) {
  await apiJson(`/api/cic-profile-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadCicProfileFile(id: string, filename: string) {
  const response = await api.get(`/api/cic-profile-jobs/${id}/files/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
    anchor.remove()
  }, 1000)
}

export async function fetchCicProfileCif(id: string): Promise<string | null> {
  try {
    const response = await api.get(`/api/cic-profile-jobs/${id}/files/pred.cif`, { responseType: 'text' })
    const text = typeof response.data === 'string' ? response.data : String(response.data ?? '')
    return text.includes('data_') || text.includes('_atom_site') ? text : null
  } catch {
    return null
  }
}
