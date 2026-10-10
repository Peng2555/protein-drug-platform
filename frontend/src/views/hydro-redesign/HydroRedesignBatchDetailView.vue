<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadHydroRedesignBatchCsv,
  fetchHydroRedesignBatch,
  fetchHydroRedesignBatchJobs,
} from '@/api/hydroRedesign'
import type { BatchDetail, Job } from '@/api/types'
import BatchDetailFrame from '@/components/layout/BatchDetailFrame.vue'
import { usePolling } from '@/composables/usePolling'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const batch = ref<BatchDetail | null>(null)
const jobs = ref<Job[]>([])

const batchId = computed(() => route.params.id as string)
const busy = computed(() => ['queued', 'running', 'partial'].includes(batch.value?.status || ''))

function summaryVal(job: Job, key: string) {
  const summary = (job.results_json?.summary || {}) as Record<string, unknown>
  return summary[key]
}

function fmt(v: unknown) {
  if (v == null || v === '') return '—'
  return String(v)
}

async function load() {
  const id = batchId.value
  try {
    batch.value = await fetchHydroRedesignBatch(id)
    const data = await fetchHydroRedesignBatchJobs(id)
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
    await downloadHydroRedesignBatchCsv(batch.value.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}
</script>

<template>
  <BatchDetailFrame v-if="batch" :batch="batch" kicker="抗体疏水性改造 · 批量">
    <template #actions>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" :disabled="!batch.done_count" @click="exportCsv">导出 CSV</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'hydro-redesign-new' })">
          新建任务
        </el-button>
    </template>
    <el-table
      :data="jobs"
      stripe
      @row-click="(row: Job) => router.push({ name: 'hydro-redesign-task', params: { id: row.id } })"
    >
      <el-table-column label="分子" min-width="120">
        <template #default="{ row }">{{ row.heavy_chain_id || row.name }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ statusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="疏水斑" width="88">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_patches')) }}</template>
      </el-table-column>
      <el-table-column label="表面疏水" width="96">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_surface_hydro')) }}</template>
      </el-table-column>
      <el-table-column label="可突变位" width="96">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_mutable_sites')) }}</template>
      </el-table-column>
      <el-table-column label="突变数" width="88">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_mutations')) }}</template>
      </el-table-column>
      <el-table-column label="湿实验" width="88">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_wetlab')) }}</template>
      </el-table-column>
      <el-table-column label="冻 CDR 跳过" width="110">
        <template #default="{ row }">{{ fmt(summaryVal(row as Job, 'n_skipped_cdr')) }}</template>
      </el-table-column>
    </el-table>
    <template #hint>点击一行打开单条改造详情。</template>
  </BatchDetailFrame>
</template>
