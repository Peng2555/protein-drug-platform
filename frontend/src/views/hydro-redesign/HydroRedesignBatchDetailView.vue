<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadHydroRedesignBatchCsv,
  fetchHydroRedesignBatch,
  fetchHydroRedesignBatchJobs,
} from '@/api/hydroRedesign'
import type { BatchDetail, Job } from '@/api/types'
import { batchStatusLabel, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const batch = ref<BatchDetail | null>(null)
const jobs = ref<Job[]>([])
let timer: ReturnType<typeof setInterval> | null = null

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

function poll() {
  if (timer) clearInterval(timer)
  if (busy.value) timer = setInterval(() => void load(), 5000)
}

watch(batchId, async () => {
  batch.value = null
  jobs.value = []
  await load()
  poll()
})
watch(() => batch.value?.status, poll)
onMounted(async () => {
  await load()
  poll()
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
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
  <div v-if="batch" class="hydro-page">
    <header class="hydro-top">
      <div>
        <p class="kicker">抗体疏水性改造 · 批量</p>
        <h1>{{ batch.name }}</h1>
        <p class="meta">
          {{ new Date(batch.created_at).toLocaleString('zh-CN') }}
          · {{ batch.done_count }}/{{ batch.heavy_chain_count }} 完成
          · 运行 {{ batch.running_count }} · 排队 {{ batch.queued_count }} · 失败 {{ batch.failed_count }}
        </p>
      </div>
      <div class="actions">
        <span class="status-pill" :data-status="batch.status">{{ batchStatusLabel(batch.status) }}</span>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" :disabled="!batch.done_count" @click="exportCsv">导出 CSV</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'hydro-redesign-new' })">
          新建任务
        </el-button>
      </div>
    </header>
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
    <p class="hint">点击一行打开单条改造详情。</p>
  </div>
</template>

<style scoped lang="scss">
.hydro-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2.5rem;
}
.hydro-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  h1 {
    margin: 0.15rem 0 0;
    font-size: 1.45rem;
  }
}
.kicker {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.meta {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
}
.status-pill {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: #f3f4f6;
  &[data-status='done'] {
    background: #ecfdf5;
    color: #047857;
  }
  &[data-status='running'],
  &[data-status='queued'],
  &[data-status='partial'] {
    background: #fff7ed;
    color: #c2410c;
  }
  &[data-status='failed'] {
    background: #fef2f2;
    color: #b91c1c;
  }
}
.hint {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
