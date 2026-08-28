import { api, apiJson } from './client'
import type { RosettaEvalJob, RosettaEvalJobListOut } from './types'

export type RosettaEvalCreateBody = {
  name?: string | null
  wt_fold_job_id?: string | null
  mutant_fold_job_ids?: string[]
  nstruct?: number
  n_jobs?: number
  antibody_chains?: string
  antigen_chains?: string
}

export async function fetchRosettaEvalJobs(limit = 50) {
  return apiJson<RosettaEvalJobListOut>(`/api/rosetta-eval-jobs?limit=${limit}`)
}

export async function fetchRosettaEvalJob(id: string) {
  return apiJson<RosettaEvalJob>(`/api/rosetta-eval-jobs/${id}`)
}

export async function createRosettaEvalJob(body: RosettaEvalCreateBody) {
  return apiJson<RosettaEvalJob>('/api/rosetta-eval-jobs', { method: 'POST', data: body })
}

export async function uploadRosettaEvalJob(
  wt: File,
  mutants: File[],
  body: RosettaEvalCreateBody,
) {
  const fd = new FormData()
  fd.append('wt', wt)
  mutants.forEach((file) => fd.append('mutants', file))
  if (body.name) fd.append('name', body.name)
  fd.append('nstruct', String(body.nstruct ?? 3))
  fd.append('n_jobs', String(body.n_jobs ?? 16))
  fd.append('antibody_chains', body.antibody_chains ?? '')
  fd.append('antigen_chains', body.antigen_chains ?? '')
  return apiJson<RosettaEvalJob>('/api/rosetta-eval-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteRosettaEvalJob(id: string) {
  await apiJson(`/api/rosetta-eval-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadRosettaEvalFile(id: string, filename: string) {
  const response = await api.get(`/api/rosetta-eval-jobs/${id}/files/${encodeURIComponent(filename)}`, {
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
