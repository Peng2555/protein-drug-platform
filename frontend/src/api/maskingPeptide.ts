import { api, apiJson } from './client'
import type {
  MaskingPeptideJob,
  MaskingPeptideJobListOut,
  MaskingPeptideSequencesOut,
} from './types'

export type MaskingPeptideCreateBody = {
  name?: string | null
  fold_job_id?: string | null
  hotspot_res?: string[]
  target_chain?: string
  peptide_length?: string
  total_designs?: number
  mpnn_rounds?: number
  skip_backbone?: boolean
  relax_jobs?: number
}

export async function fetchMaskingPeptideJobs(limit = 50) {
  return apiJson<MaskingPeptideJobListOut>(`/api/masking-peptide-jobs?limit=${limit}`)
}

export async function fetchMaskingPeptideJob(id: string) {
  return apiJson<MaskingPeptideJob>(`/api/masking-peptide-jobs/${id}`)
}

export async function fetchMaskingPeptideSequences(id: string) {
  return apiJson<MaskingPeptideSequencesOut>(`/api/masking-peptide-jobs/${id}/sequences`)
}

export async function createMaskingPeptideJob(body: MaskingPeptideCreateBody) {
  return apiJson<MaskingPeptideJob>('/api/masking-peptide-jobs', { method: 'POST', data: body })
}

export async function uploadMaskingPeptideJob(
  antibodyPdb: File,
  body: MaskingPeptideCreateBody,
) {
  const fd = new FormData()
  fd.append('antibody_pdb', antibodyPdb)
  if (body.name) fd.append('name', body.name)
  if (body.fold_job_id) fd.append('fold_job_id', body.fold_job_id)
  fd.append('hotspot_res', (body.hotspot_res ?? []).join(','))
  fd.append('target_chain', body.target_chain ?? 'H')
  fd.append('peptide_length', body.peptide_length ?? '12-18')
  fd.append('total_designs', String(body.total_designs ?? 200))
  fd.append('mpnn_rounds', String(body.mpnn_rounds ?? 4))
  fd.append('skip_backbone', String(Boolean(body.skip_backbone)))
  fd.append('relax_jobs', String(body.relax_jobs ?? 8))
  return apiJson<MaskingPeptideJob>('/api/masking-peptide-jobs/upload', { method: 'POST', data: fd })
}

export async function deleteMaskingPeptideJob(id: string) {
  await apiJson(`/api/masking-peptide-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadMaskingPeptideFile(id: string, filename: string) {
  const response = await api.get(
    `/api/masking-peptide-jobs/${id}/files/${encodeURIComponent(filename)}`,
    { responseType: 'blob' },
  )
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
