import { api, apiJson } from './client'
import type { DockingJob, DockingJobListOut } from './types'

export async function fetchDockingJobs(limit = 50) {
  return apiJson<DockingJobListOut>(`/api/docking-jobs?limit=${limit}`)
}

export async function fetchDockingJob(id: string) {
  return apiJson<DockingJob>(`/api/docking-jobs/${id}`)
}

export async function submitDockingJob(
  receptor: File,
  ligandSmiles: string,
  referenceLigand: File | null,
  params: {
    name?: string
    engine: string
    center_x: number
    center_y: number
    center_z: number
    size_x: number
    size_y: number
    size_z: number
    exhaustiveness: number
    num_modes: number
    energy_range: number
    box_padding: number
    n_starts: number
    n_conformers: number
  },
) {
  const fd = new FormData()
  fd.append('receptor', receptor)
  fd.append('ligand_smiles', ligandSmiles.trim())
  if (referenceLigand) fd.append('reference_ligand', referenceLigand)
  Object.entries(params).forEach(([key, value]) => fd.append(key, String(value)))
  return apiJson<DockingJob>('/api/docking-jobs', { method: 'POST', data: fd })
}

export async function deleteDockingJob(id: string) {
  await apiJson(`/api/docking-jobs/${id}`, { method: 'DELETE' })
}

export async function downloadDockingFile(id: string, filename: string) {
  const response = await api.get(`/api/docking-jobs/${id}/files/${encodeURIComponent(filename)}`, {
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
