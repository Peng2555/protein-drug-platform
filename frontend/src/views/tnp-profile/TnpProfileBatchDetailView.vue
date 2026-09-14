<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadTnpProfileBatchCsv,
  fetchTnpProfileBatch,
  fetchTnpProfileBatchJobs,
} from '@/api/tnpProfile'
import type { BatchDetail, Job } from '@/api/types'
import { batchStatusLabel, statusLabel } from '@/utils/constants'

const FLAG_ZH: Record<string, string> = { green: '绿', amber: '黄', red: '红', pending: '—' }

const route = useRoute()
const router = useRouter()
const batch = ref<BatchDetail | null>(null)
const jobs = ref<Job[]>([])
let timer: ReturnType<typeof setInterval> | null = null

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
    await downloadTnpProfileBatchCsv(batch.value.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}
</script>

<template>
  <div v-if="batch" class="tnp-page">
    <header class="tnp-top">
      <div>
        <p class="kicker">VHH 可开发性画像 · 批量</p>
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
        <el-button size="small" type="primary" plain @click="router.push({ name: 'tnp-profile-new' })">新建任务</el-button>
      </div>
    </header>
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
    <p class="hint">点击一行打开单条画像详情。</p>
  </div>
</template>

<style scoped lang="scss">
.tnp-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2.5rem;
}
.tnp-top {
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
.hint {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
