import { apiJson } from './client'
import type { MdJob, MdJobListOut } from './types'

export async function fetchMdJobs(limit = 50) {
  return apiJson<MdJobListOut>(`/api/md-jobs?limit=${limit}`)
}

export async function fetchMdJob(id: string) {
  return apiJson<MdJob>(`/api/md-jobs/${id}`)
}

export async function createMdJob(body: {
  parent_job_id?: string | null
  structure_path?: string | null
  name?: string | null
  production_ns?: number
  replicas?: number
  antigen_chain?: string
  binder_chain?: string
}) {
  return apiJson<MdJob>('/api/md-jobs', { method: 'POST', data: body })
}

export async function uploadMdStructure(
  file: File,
  meta: {
    name?: string | null
    production_ns?: number
    replicas?: number
    antigen_chain?: string
    binder_chain?: string
  },
) {
  const fd = new FormData()
  fd.append('file', file)
  if (meta.name) fd.append('name', meta.name)
  if (meta.production_ns != null) fd.append('production_ns', String(meta.production_ns))
  if (meta.replicas != null) fd.append('replicas', String(meta.replicas))
  if (meta.antigen_chain) fd.append('antigen_chain', meta.antigen_chain)
  if (meta.binder_chain) fd.append('binder_chain', meta.binder_chain)
  return apiJson<MdJob>('/api/md-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteMdJob(id: string) {
  await apiJson(`/api/md-jobs/${id}`, { method: 'DELETE' })
}
