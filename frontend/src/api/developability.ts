import { api, apiJson } from './client'
import type { DevelopabilityJob, DevelopabilityJobListOut } from './types'

export async function fetchDevelopabilityJobs(limit = 50) {
  return apiJson<DevelopabilityJobListOut>(`/api/developability-jobs?limit=${limit}`)
}

export async function fetchDevelopabilityJob(id: string) {
  return apiJson<DevelopabilityJob>(`/api/developability-jobs/${id}`)
}

export async function createDevelopabilityJob(body: {
  fasta: string
  name?: string | null
  goal: 'hydro' | 'tm' | 'both'
  freeze_cysteine: boolean
  freeze_cdr3: boolean
  freeze_all_cdrs: boolean
  dll_threshold: number
  max_mutants_per_site: number
}) {
  return apiJson<DevelopabilityJob>('/api/developability-jobs', { method: 'POST', data: body })
}

export async function resubmitDevelopabilityJob(id: string) {
  return apiJson<DevelopabilityJob>(`/api/developability-jobs/${id}/resubmit`, { method: 'POST' })
}

export async function deleteDevelopabilityJob(id: string) {
  await apiJson(`/api/developability-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadDevelopabilityFile(id: string, filename: string) {
  const response = await api.get(`/api/developability-jobs/${id}/files/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
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
