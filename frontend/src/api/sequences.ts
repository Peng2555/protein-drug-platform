import { apiJson } from './client'
import type { JobSequencesOut } from './types'

export async function fetchJobSequences(jobId: string) {
  return apiJson<JobSequencesOut>(`/api/jobs/${jobId}/sequences`)
}
