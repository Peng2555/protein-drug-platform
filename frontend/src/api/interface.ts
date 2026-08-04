import { apiJson } from './client'
import type { JobInterfaceData } from '@/types/structure'

export async function fetchJobInterface(jobId: string) {
  return apiJson<JobInterfaceData>(`/api/jobs/${jobId}/interface`)
}
