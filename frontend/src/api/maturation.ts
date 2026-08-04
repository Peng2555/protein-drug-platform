import { apiJson } from './client'
import type { MaturationJob, MaturationJobListOut, MaturationVariantsOut } from './types'

export async function fetchMaturationJobs(limit = 50) {
  return apiJson<MaturationJobListOut>(`/api/maturation-jobs?limit=${limit}`)
}

export async function fetchMaturationJob(id: string) {
  return apiJson<MaturationJob>(`/api/maturation-jobs/${id}`)
}

export async function createMaturationJob(body: {
  fasta: string
  name?: string | null
  structure_source: 'upload' | 'boltz2' | 'esmfold2' | 'fold_job'
  fold_job_id?: string | null
  binder_chain_id?: string
  antigen_chain_id?: string
  cdr_mask?: string[]
  use_msa_server?: boolean
  iggm?: {
    num_samples?: number
    steps?: number
    max_antigen_size?: number
    temperature?: number
    chunk_size?: number
    relax?: boolean
    gpu_count?: number
    gpu_ids?: number[] | null
    epitope?: number[] | null
  }
  fold_params?: Record<string, unknown> | null
}) {
  return apiJson<MaturationJob>('/api/maturation-jobs', { method: 'POST', data: body })
}

export async function uploadMaturationJob(
  fasta: string,
  structure: File,
  meta: {
    name?: string | null
    binder_chain_id?: string
    antigen_chain_id?: string
    cdr_mask?: string
    num_samples?: number
    steps?: number
    max_antigen_size?: number
    temperature?: number
    chunk_size?: number
    relax?: boolean
    gpu_count?: number
  },
) {
  const fd = new FormData()
  fd.append('fasta', fasta)
  fd.append('structure', structure)
  if (meta.name) fd.append('name', meta.name)
  if (meta.binder_chain_id) fd.append('binder_chain_id', meta.binder_chain_id)
  if (meta.antigen_chain_id) fd.append('antigen_chain_id', meta.antigen_chain_id)
  if (meta.cdr_mask) fd.append('cdr_mask', meta.cdr_mask)
  if (meta.num_samples != null) fd.append('num_samples', String(meta.num_samples))
  if (meta.steps != null) fd.append('steps', String(meta.steps))
  if (meta.max_antigen_size != null) fd.append('max_antigen_size', String(meta.max_antigen_size))
  if (meta.temperature != null) fd.append('temperature', String(meta.temperature))
  if (meta.chunk_size != null) fd.append('chunk_size', String(meta.chunk_size))
  fd.append('relax', meta.relax ? 'true' : 'false')
  if (meta.gpu_count != null) fd.append('gpu_count', String(meta.gpu_count))
  return apiJson<MaturationJob>('/api/maturation-jobs/upload', { method: 'POST', data: fd })
}

export async function fetchMaturationVariants(
  jobId: string,
  limit = 100,
  offset = 0,
  minFrequency = 0,
) {
  const q = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    min_frequency: String(minFrequency),
  })
  return apiJson<MaturationVariantsOut>(`/api/maturation-jobs/${jobId}/variants?${q}`)
}

export function maturationVariantsCsvUrl(jobId: string) {
  return `/api/maturation-jobs/${jobId}/variants.csv`
}

export async function deleteMaturationJob(id: string) {
  await apiJson(`/api/maturation-jobs/${id}`, { method: 'DELETE' })
}
