<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteMdJob, fetchMdJob } from '@/api/md'
import MetricsGrid from '@/components/fold/MetricsGrid.vue'
import { useFoldTasksStore } from '@/stores/foldTasks'
import type { MdJob } from '@/api/types'
import { MD_STAGE_LABELS, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const foldStore = useFoldTasksStore()

const loading = ref(true)
const job = ref<MdJob | null>(null)
const jobId = computed(() => route.params.id as string)

const mdStages = ['prep', 'topo', 'equil', 'prod', 'analysis', 'done']

const stagePills = computed(() => {
  const j = job.value
  if (!j) return []
  const current = j.stage || 'queued'
  const currentIdx = mdStages.indexOf(current)
  return mdStages.map((s, i) => {
    let state: 'done' | 'active' | '' = ''
    if (j.status === 'done' || i < currentIdx) state = 'done'
    else if (s === current || (current === 'queued' && s === 'prep' && j.status === 'running')) {
      state = 'active'
    }
    return { stage: s, label: MD_STAGE_LABELS[s] || s, state }
  })
})

const metrics = computed(() => {
  const j = job.value
  if (!j) return []
  const params = (j.params_json || {}) as Record<string, unknown>
  return [
    { label: '阶段', value: MD_STAGE_LABELS[j.stage || ''] || j.stage || '—' },
    { label: '生产 (ns)', value: params.production_ns as number | undefined },
    { label: '复本数', value: params.replicas as number | undefined },
    {
      label: '耗时',
      value: j.runtime_seconds != null ? `${Math.round(j.runtime_seconds)}s` : null,
    },
  ]
})

const detailMeta = computed(() => {
  const j = job.value
  if (!j) return ''
  const params = (j.params_json || {}) as Record<string, unknown>
  return [
    `${params.production_ns ?? '?'} ns × ${params.replicas ?? '?'} 复本`,
    params.antigen_chain && params.binder_chain
      ? `链 ${params.binder_chain}+${params.antigen_chain}`
      : null,
    j.parent_job_id ? `来源折叠 ${j.parent_job_id.slice(0, 8)}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
})

const summaryText = computed(() => {
  const j = job.value
  if (!j) return ''
  if (j.results_json) return JSON.stringify(j.results_json, null, 2)
  if (j.status === 'running') return '模拟进行中，完成后将显示界面分析摘要…'
  return '暂无分析结果'
})

async function loadDetail(silent = false) {
  if (!silent) loading.value = true
  try {
    job.value = await fetchMdJob(jobId.value)
  } catch (e) {
    job.value = null
    if (!silent) ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onDelete() {
  const j = job.value
  if (!j) return
  try {
    await ElMessageBox.confirm(
      `确定删除 MD 任务「${j.name || j.id.slice(0, 8)}」吗？`,
      '删除任务',
      { type: 'warning' },
    )
    await deleteMdJob(j.id)
    await foldStore.refreshMdTasks()
    router.push({ name: 'md' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

let pollHandle: ReturnType<typeof setInterval> | null = null

watch(jobId, () => void loadDetail())

watch(
  () => job.value?.status,
  (status) => {
    if (pollHandle) clearInterval(pollHandle)
    if (status && ['queued', 'running'].includes(status)) {
      pollHandle = setInterval(() => void loadDetail(true), 5000)
    }
  },
)

onMounted(async () => {
  await loadDetail()
  foldStore.startPolling(async () => {
    if (job.value && ['queued', 'running'].includes(job.value.status)) {
      await loadDetail(true)
    }
  })
})

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<template>
  <div v-loading="loading" class="detail-panel page-card page-card--accent">
    <template v-if="job">
      <div class="detail-head">
        <div class="detail-title-block">
          <h2>{{ job.name || job.id }}</h2>
          <p class="detail-meta">{{ detailMeta }}</p>
        </div>
        <div class="detail-actions">
          <el-tag :type="statusTagType(job.status)" size="small">
            {{ statusLabel(job.status) }}
          </el-tag>
          <el-button size="small" type="danger" plain @click="onDelete">删除</el-button>
        </div>
      </div>

      <div class="md-stage-bar">
        <span
          v-for="pill in stagePills"
          :key="pill.stage"
          class="md-stage-pill"
          :class="pill.state"
        >
          {{ pill.label }}
        </span>
      </div>

      <div v-if="job.error_message" class="error-box">{{ job.error_message }}</div>

      <MetricsGrid :items="metrics" />

      <div class="md-summary-box">{{ summaryText }}</div>
    </template>
    <el-empty v-else description="MD 任务不存在" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
</style>
