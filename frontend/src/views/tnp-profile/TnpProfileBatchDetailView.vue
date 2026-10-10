<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadTnpProfileBatchCsv,
  fetchTnpProfileBatch,
  fetchTnpProfileBatchJobs,
} from '@/api/tnpProfile'
import type { BatchDetail, Job } from '@/api/types'
import BatchDetailFrame from '@/components/layout/BatchDetailFrame.vue'
import { usePolling } from '@/composables/usePolling'
import { statusLabel } from '@/utils/constants'

const FLAG_ZH: Record<string, string> = { green: '绿', amber: '黄', red: '红', pending: '—' }

const route = useRoute()
const router = useRouter()
const batch = ref<BatchDetail | null>(null)
const jobs = ref<Job[]>([])

const batchId = computed(() => route.params.id as string)
const busy = computed(() =>
  ['queued', 'running'].includes(batch.value?.status || ''),
)

function flagOf(job: Job, id: string) {
  const summary = (job.results_json?.summary || {}) as Record<string, unknown>
  const metrics = (summary.metrics as Array<{ id: string; flag?: string; value?: number }> | undefined) || []
  return metrics.find((m) => m.id === id)
}

function summaryVal(job: Job, key: string) {
  const summary = (job.results_json?.summary || {}) as Record<string, unknown>
  return summary[key]
}

function fmt(v: unknown, digits = 2) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  if (Number.isInteger(n)) return String(n)
  return n.toFixed(digits)
}

async function load() {
  const id = batchId.value
  try {
    batch.value = await fetchTnpProfileBatch(id)
    const data = await fetchTnpProfileBatchJobs(id)
    jobs.value = data.items
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}

const { refresh } = usePolling(load, busy)

watch(batchId, async () => {
  batch.value = null
  jobs.value = []
  await refresh()
})

async function exportCsv() {
  if (!batch.value) return
  try {
    await downloadTnpProfileBatchCsv(batch.value.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}
</script>

<template>
  <BatchDetailFrame v-if="batch" :batch="batch" kicker="VHH 可开发性画像 · 批量">
    <template #actions>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" :disabled="!batch.done_count" @click="exportCsv">导出 CSV</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'tnp-profile-new' })">新建任务</el-button>
    </template>
    <el-table :data="jobs" stripe @row-click="(row: Job) => router.push({ name: 'tnp-profile-task', params: { id: row.id } })">
      <el-table-column label="分子" min-width="120">
        <template #default="{ row }">{{ row.heavy_chain_id || row.name }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ statusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="Tetrad" width="90">
        <template #default="{ row }">{{ summaryVal(row as Job, 'tetrad_motif') || '—' }}</template>
      </el-table-column>
      <el-table-column v-for="key in ['L', 'L3', 'C', 'PSH', 'PPC', 'PNC']" :key="key" :label="key" min-width="88">
        <template #default="{ row }">
          <span class="cell-flag" :data-flag="flagOf(row as Job, key)?.flag || ''">
            {{ fmt(flagOf(row as Job, key)?.value ?? summaryVal(row as Job, key)) }}
            {{ FLAG_ZH[flagOf(row as Job, key)?.flag || ''] || '' }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <template #hint>点击一行打开单条画像详情。</template>
  </BatchDetailFrame>
</template>

<style scoped lang="scss">
.cell-flag {
  &[data-flag='green'] {
    color: #047857;
  }
  &[data-flag='amber'] {
    color: #c2410c;
  }
  &[data-flag='red'] {
    color: #b91c1c;
  }
}
</style>
