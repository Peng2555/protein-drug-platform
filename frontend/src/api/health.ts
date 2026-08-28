import { apiJson } from './client'

export interface PlatformHealth {
  status: string
  database: string
  redis: string
  queue_depth: number | null
  running_jobs: number | null
  gpu_workers: number | null
}

export async function fetchPlatformHealth() {
  return apiJson<PlatformHealth>('/api/health')
}
