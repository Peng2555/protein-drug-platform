import { api, apiJson } from './client'
import type {
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
