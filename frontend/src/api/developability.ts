import { api, apiJson } from './client'
import type { DevelopabilityJob, DevelopabilityJobListOut } from './types'

export type DevelopabilityCreateBody = {
  fasta: string
  name?: string | null
  goal: 'hydro' | 'tm' | 'both'
  freeze_cysteine: boolean
  freeze_cdr3: boolean
  freeze_all_cdrs: boolean
  dll_threshold: number
  max_mutants_per_site: number
  run_maxwell?: boolean
  fold_job_id?: string | null
}

export async function fetchDevelopabilityJobs(limit = 50) {
  return apiJson<DevelopabilityJobListOut>(`/api/developability-jobs?limit=${limit}`)
}

export async function fetchDevelopabilityJob(id: string) {
  return apiJson<DevelopabilityJob>(`/api/developability-jobs/${id}`)
}

export async function createDevelopabilityJob(body: DevelopabilityCreateBody) {
  return apiJson<DevelopabilityJob>('/api/developability-jobs', { method: 'POST', data: body })
}

export async function uploadDevelopabilityJob(structure: File, body: DevelopabilityCreateBody) {
  const fd = new FormData()
  fd.append('structure', structure)
  fd.append('fasta', body.fasta)
  if (body.name) fd.append('name', body.name)
  fd.append('goal', body.goal)
  fd.append('freeze_cysteine', body.freeze_cysteine ? 'true' : 'false')
  fd.append('freeze_cdr3', body.freeze_cdr3 ? 'true' : 'false')
  fd.append('freeze_all_cdrs', body.freeze_all_cdrs ? 'true' : 'false')
  fd.append('dll_threshold', String(body.dll_threshold))
  fd.append('max_mutants_per_site', String(body.max_mutants_per_site))
  fd.append('run_maxwell', body.run_maxwell === false ? 'false' : 'true')
  return apiJson<DevelopabilityJob>('/api/developability-jobs/upload', { method: 'POST', data: fd })
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
