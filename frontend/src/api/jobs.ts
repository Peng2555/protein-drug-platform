import { api, apiJson } from './client'
import type { Job, JobListOut } from './types'

export async function fetchJobs(limit = 50, singlesOnly = true) {
  const data = await apiJson<JobListOut>(
    `/api/jobs?limit=${limit}&singles_only=${singlesOnly}`,
  )
  return data
}

export async function fetchJob(id: string) {
  return apiJson<Job>(`/api/jobs/${id}`)
}

export async function createJob(body: {
  fasta?: string
  name?: string | null
  engine: string
  use_msa_server: boolean
  boltz_params?: Record<string, unknown>
  esmfold_params?: Record<string, number>
  components?: Array<Record<string, unknown>>
  constraints?: Array<Record<string, unknown>>
  affinity?: { binder: string } | null
}) {
  return apiJson<Job>('/api/jobs', { method: 'POST', data: body })
}

export async function deleteJob(id: string) {
  await apiJson(`/api/jobs/${id}`, { method: 'DELETE' })
}

export async function fetchStructureText(jobId: string): Promise<string> {
  const resp = await api.get<string>(`/api/jobs/${jobId}/structure`, {
    responseType: 'text',
    transformResponse: [(data) => data],
  })
  return resp.data
}

export async function downloadStructure(jobId: string, filename: string) {
  const resp = await api.get<Blob>(`/api/jobs/${jobId}/structure`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename.replace(/[^\w.-]+/g, '_')}.cif`
  a.click()
  URL.revokeObjectURL(url)
}
