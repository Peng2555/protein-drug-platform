import { apiJson } from './client'
import type { RasDockingJob, RasDockingJobListOut } from './types'

export async function fetchRasDockingJobs(limit = 50) {
  return apiJson<RasDockingJobListOut>(`/api/ras-docking-jobs?limit=${limit}`)
}

export async function fetchRasDockingJob(id: string) {
  return apiJson<RasDockingJob>(`/api/ras-docking-jobs/${id}`)
}

export async function createRasDockingJob(body: {
  name?: string | null
  project: 'rmc6236' | 'rmc6291'
  stage: string
  system?: string
}) {
  return apiJson<RasDockingJob>('/api/ras-docking-jobs', {
    method: 'POST',
    data: body,
  })
}

export async function uploadRasCandidate(file: File, name?: string | null) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('project', 'rmc6236')
  if (name) fd.append('name', name)
  return apiJson<RasDockingJob>('/api/ras-docking-jobs/screen', {
    method: 'POST',
    data: fd,
  })
}

export async function deleteRasDockingJob(id: string) {
  await apiJson(`/api/ras-docking-jobs/${id}`, { method: 'DELETE' })
}
