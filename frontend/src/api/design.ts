import { api, apiJson } from './client'
import type { DesignJob, DesignJobListOut } from './types'

export type DesignCreateBody = {
  name?: string | null
  fold_job_id?: string | null
  designed_chains?: string
  num_seq_per_target?: number
  sampling_temp?: number
  seed?: number
  backbone_noise?: number
  omit_aas?: string
}

export async function fetchDesignJobs(limit = 50) {
  return apiJson<DesignJobListOut>(`/api/design-jobs?limit=${limit}`)
}

export async function fetchDesignJob(id: string) {
  return apiJson<DesignJob>(`/api/design-jobs/${id}`)
}

export async function createDesignJob(body: DesignCreateBody) {
  return apiJson<DesignJob>('/api/design-jobs', { method: 'POST', data: body })
}

export async function uploadDesignJob(structure: File, body: DesignCreateBody) {
  const fd = new FormData()
  fd.append('structure', structure)
  if (body.name) fd.append('name', body.name)
  fd.append('designed_chains', body.designed_chains ?? '')
  fd.append('num_seq_per_target', String(body.num_seq_per_target ?? 8))
  fd.append('sampling_temp', String(body.sampling_temp ?? 0.1))
  fd.append('seed', String(body.seed ?? 0))
  fd.append('backbone_noise', String(body.backbone_noise ?? 0))
  fd.append('omit_aas', body.omit_aas ?? 'X')
  return apiJson<DesignJob>('/api/design-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteDesignJob(id: string) {
  await apiJson(`/api/design-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadDesignFile(id: string, filename: string) {
  const response = await api.get(`/api/design-jobs/${id}/files/${encodeURIComponent(filename)}`, {
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
