import { apiJson } from './client'
import type {
  SynthesisCandidatesOut,
  SynthesisJob,
  SynthesisJobListOut,
  SynthesisSelectOut,
} from './types'

export async function fetchSynthesisJobs(limit = 50) {
  return apiJson<SynthesisJobListOut>(`/api/synthesis-jobs?limit=${limit}`)
}

export async function fetchSynthesisJob(id: string) {
  return apiJson<SynthesisJob>(`/api/synthesis-jobs/${id}`)
}

export async function runSynthesisJob(
  shmTable: File,
  iggmTable: File,
  params: {
    name?: string | null
    originFasta?: File | null
    min_seq_count?: number
    min_extra_count?: number
    chain_id?: string
    v_gene?: string
  } = {},
) {
  const fd = new FormData()
  fd.append('shm_table', shmTable)
  fd.append('iggm_table', iggmTable)
  if (params.originFasta) fd.append('origin_fasta', params.originFasta)
  if (params.name) fd.append('name', params.name)
  if (params.min_seq_count != null) fd.append('min_seq_count', String(params.min_seq_count))
  if (params.min_extra_count != null) fd.append('min_extra_count', String(params.min_extra_count))
  if (params.chain_id) fd.append('chain_id', params.chain_id)
  if (params.v_gene) fd.append('v_gene', params.v_gene)
  return apiJson<SynthesisSelectOut>('/api/synthesis-jobs/run', { method: 'POST', data: fd })
}

export async function fetchSynthesisCandidates(
  jobId: string,
  kind: 'order' | 'matched' = 'order',
  limit = 200,
  offset = 0,
) {
  const q = new URLSearchParams({
    kind,
    limit: String(limit),
    offset: String(offset),
  })
  return apiJson<SynthesisCandidatesOut>(`/api/synthesis-jobs/${jobId}/candidates?${q}`)
}

export function synthesisCandidatesCsvUrl(jobId: string, kind: 'order' | 'matched' = 'order') {
  return `/api/synthesis-jobs/${jobId}/candidates.csv?kind=${kind}`
}

export function synthesisOrderTxtUrl(jobId: string) {
  return `/api/synthesis-jobs/${jobId}/order.txt`
}

export async function deleteSynthesisJob(id: string) {
  await apiJson(`/api/synthesis-jobs/${id}`, { method: 'DELETE' })
}
