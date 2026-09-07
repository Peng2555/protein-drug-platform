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

export async function fetchStructureText(jobId: string, model?: number | null): Promise<string> {
  const qs = model != null && model >= 0 ? `?model=${model}` : ''
  const resp = await api.get<string>(`/api/jobs/${jobId}/structure${qs}`, {
    responseType: 'text',
    transformResponse: [(data) => data],
  })
  return resp.data
}

export async function downloadStructure(jobId: string, filename: string, model?: number | null) {
  const qs = model != null && model >= 0 ? `?model=${model}` : ''
  const resp = await api.get<Blob>(`/api/jobs/${jobId}/structure${qs}`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  const suffix = model != null && model >= 0 ? `_model_${model}` : ''
  a.download = `${filename.replace(/[^\w.-]+/g, '_')}${suffix}.cif`
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadAllStructures(jobId: string, filename: string) {
  const resp = await api.get<Blob>(`/api/jobs/${jobId}/structures.zip`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename.replace(/[^\w.-]+/g, '_')}_samples.zip`
  a.click()
  URL.revokeObjectURL(url)
}
