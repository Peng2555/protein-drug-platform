import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchBatches, fetchBatch, fetchBatchJobs } from '@/api/batches'
import { fetchJob, fetchJobs } from '@/api/jobs'
import { fetchMdJob, fetchMdJobs } from '@/api/md'
import { fetchMaturationJob, fetchMaturationJobs } from '@/api/maturation'
import type { Batch, BatchDetail, Job, MdJob, MaturationJob } from '@/api/types'
import { BATCH_JOBS_PAGE_SIZE } from '@/utils/constants'

export type TaskFilter = 'all' | 'single' | 'batch'

export const useFoldTasksStore = defineStore('foldTasks', () => {
  const jobs = ref<Job[]>([])
  const batches = ref<Batch[]>([])
  const mdJobs = ref<MdJob[]>([])
  const maturationJobs = ref<MaturationJob[]>([])
  const taskFilter = ref<TaskFilter>('all')
  const loading = ref(false)
  const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

  const hasActiveTasks = computed(() =>
    [...jobs.value, ...batches.value, ...mdJobs.value, ...maturationJobs.value].some((t) =>
      ['queued', 'running'].includes(t.status),
    ),
  )

  const mergedTaskItems = computed(() => {
    const items: Array<
      | { kind: 'single'; data: Job; ts: string }
      | { kind: 'batch'; data: Batch; ts: string }
    > = []
    if (taskFilter.value === 'all' || taskFilter.value === 'single') {
      for (const j of jobs.value) items.push({ kind: 'single', data: j, ts: j.created_at })
    }
    if (taskFilter.value === 'all' || taskFilter.value === 'batch') {
      for (const b of batches.value) items.push({ kind: 'batch', data: b, ts: b.created_at })
    }
    items.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
    return items
  })

  async function refreshFoldTasks() {
    loading.value = true
    try {
      const [j, b] = await Promise.all([fetchJobs(50, true), fetchBatches(50)])
      jobs.value = j.items
      batches.value = b.items
    } finally {
      loading.value = false
    }
  }

  async function refreshMdTasks() {
    const data = await fetchMdJobs(50)
    mdJobs.value = data.items
  }

  async function refreshMaturationTasks() {
    try {
      const data = await fetchMaturationJobs(50)
      maturationJobs.value = data.items ?? []
    } catch {
      /* keep previous list on transient API errors */
    }
  }

  async function refreshAll() {
    await Promise.all([refreshFoldTasks(), refreshMdTasks(), refreshMaturationTasks()])
    if (hasActiveTasks.value) startPolling()
  }

  function stopPolling() {
    if (pollTimer.value) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
  }

  function pollIntervalMs() {
    return hasActiveTasks.value ? 5000 : 15000
  }

  function restartPolling() {
    stopPolling()
    startPolling()
  }

  function startPolling(onTick?: () => void | Promise<void>) {
    if (pollTimer.value) return
    const tick = async () => {
      await refreshFoldTasks()
      await refreshMdTasks()
      await refreshMaturationTasks()
      await onTick?.()
      if (!hasActiveTasks.value) stopPolling()
    }
    pollTimer.value = setInterval(tick, pollIntervalMs())
  }

  return {
    jobs,
    batches,
    mdJobs,
    maturationJobs,
    taskFilter,
    loading,
    hasActiveTasks,
    mergedTaskItems,
    refreshFoldTasks,
    refreshMdTasks,
    refreshMaturationTasks,
    refreshAll,
    startPolling,
    stopPolling,
    restartPolling,
  }
})

export const useBatchDetailStore = defineStore('batchDetail', () => {
  const batch = ref<BatchDetail | null>(null)
  const batchJobs = ref<Job[]>([])
  const batchJobsTotal = ref(0)
  const batchJobsPage = ref(0)
  const loading = ref(false)

  async function loadBatch(id: string) {
    loading.value = true
    try {
      batch.value = await fetchBatch(id)
      await loadBatchJobsPage(id, 0)
    } finally {
      loading.value = false
    }
  }

  async function refreshBatch(id: string) {
    batch.value = await fetchBatch(id)
    if (batchJobsPage.value === 0) {
      await loadBatchJobsPage(id, 0)
    }
  }

  async function loadBatchJobsPage(batchId: string, page: number) {
    const offset = page * BATCH_JOBS_PAGE_SIZE
    const data = await fetchBatchJobs(batchId, BATCH_JOBS_PAGE_SIZE, offset)
    batchJobsPage.value = page
    batchJobsTotal.value = data.total
    batchJobs.value = data.items
    return data
  }

  function reset() {
    batch.value = null
    batchJobs.value = []
    batchJobsTotal.value = 0
    batchJobsPage.value = 0
  }

  return {
    batch,
    batchJobs,
    batchJobsTotal,
    batchJobsPage,
    loading,
    loadBatch,
    refreshBatch,
    loadBatchJobsPage,
    reset,
  }
})

export async function pollJobDetail(jobId: string) {
  return fetchJob(jobId)
}

export async function pollMdJobDetail(jobId: string) {
  return fetchMdJob(jobId)
}

export async function pollMaturationJobDetail(jobId: string) {
  return fetchMaturationJob(jobId)
}
