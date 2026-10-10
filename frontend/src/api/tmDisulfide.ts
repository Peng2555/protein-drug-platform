import { api, apiJson } from './client'
import { downloadBlob } from '@/utils/download'
import type {
  TmDisulfideJob,
  TmDisulfideJobListOut,
  TmDisulfideProgressOut,
  TmDisulfideRankedOut,
  TmDisulfideSourceFoldJobListOut,
} from './types'

export type TmDisulfideCreateBody = {
  name?: string | null
  source_job_id: string
}

export async function fetchTmDisulfideJobs(limit = 50) {
  return apiJson<TmDisulfideJobListOut>(`/api/tm-disulfide-jobs?limit=${limit}`)
}

export async function fetchTmDisulfideJob(id: string) {
  return apiJson<TmDisulfideJob>(`/api/tm-disulfide-jobs/${id}`)
}

export async function fetchTmDisulfideProgress(id: string) {
  return apiJson<TmDisulfideProgressOut>(`/api/tm-disulfide-jobs/${id}/progress`)
}

export async function fetchTmDisulfideRanked(id: string) {
  return apiJson<TmDisulfideRankedOut>(`/api/tm-disulfide-jobs/${id}/ranked`)
}

export async function fetchTmDisulfideSourceFoldJobs(limit = 50) {
  return apiJson<TmDisulfideSourceFoldJobListOut>(`/api/tm-disulfide-jobs/source-fold-jobs?limit=${limit}`)
}

export async function createTmDisulfideJob(body: TmDisulfideCreateBody) {
  return apiJson<TmDisulfideJob>('/api/tm-disulfide-jobs', { method: 'POST', data: body })
}

export async function deleteTmDisulfideJob(id: string) {
  await apiJson(`/api/tm-disulfide-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadTmDisulfideFile(id: string, filename: string) {
  const response = await api.get(`/api/tm-disulfide-jobs/${id}/files/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  })
  downloadBlob(response.data, filename)
}
