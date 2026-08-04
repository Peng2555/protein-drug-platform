<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteJob, downloadStructure, fetchJob } from '@/api/jobs'
import { fetchJobSequences } from '@/api/sequences'
import MetricsGrid from '@/components/fold/MetricsGrid.vue'
import SequencePanel from '@/components/sequence/SequencePanel.vue'
import InterfacePanel from '@/components/structure/InterfacePanel.vue'
import StructureViewer from '@/components/structure/StructureViewer.vue'
import { useSelectionStore } from '@/composables/useSelection'
import { useFoldTasksStore } from '@/stores/foldTasks'
import type { Job } from '@/api/types'
import type { ChainSequence } from '@/api/types'
import type { InterfaceChainMeta } from '@/types/structure'
import { engineLabel, formatEsmfoldParams, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const foldStore = useFoldTasksStore()
const selectionStore = useSelectionStore()

const loading = ref(true)
const job = ref<Job | null>(null)
const sequences = ref<ChainSequence[]>([])
const cifText = ref<string | null>(null)
const returnBatchId = ref<string | null>(
  typeof route.query.batch === 'string' ? route.query.batch : null,
)

const jobId = computed(() => route.params.id as string)

const chainCount = computed(() => Object.keys(job.value?.chains_json || {}).length)

const interfaceChains = computed((): InterfaceChainMeta[] | null => {
  if (!sequences.value.length) return null
  const palette = ['#5b8def', '#e07a5f', '#22c55e', '#a855f7', '#f59e0b']
  return sequences.value.map((ch, i) => ({
    chain_id: ch.chain_id,
    length: ch.length,
    label: ch.is_antibody ? `${ch.domain} (${ch.chain_id})` : `链 ${ch.chain_id}`,
    role: ch.is_antibody ? 'binder' : i === 0 ? 'target' : 'other',
    color: palette[i % palette.length],
    is_antibody: ch.is_antibody,
  }))
})

const metrics = computed(() => {
  const j = job.value
  if (!j) return []
  return [
    { label: 'ipTM', value: j.iptm, highlight: true },
    { label: 'pDockQ', value: j.pdockq, highlight: j.pdockq != null },
    { label: 'pDockQ2', value: j.pdockq2, highlight: j.pdockq2 != null },
    { label: 'pTM', value: j.ptm },
    { label: 'pLDDT', value: j.complex_plddt, highlight: true },
    { label: '置信度', value: j.confidence_score },
    {
      label: '耗时',
      value: j.runtime_seconds != null ? `${Math.round(j.runtime_seconds)}s` : null,
    },
  ]
})

const detailMeta = computed(() => {
  const j = job.value
  if (!j) return ''
  const chains = Object.entries(j.chains_json || {})
    .map(([k, v]) => `${k}:${v}`)
    .join(' · ')
  const created = j.created_at ? new Date(j.created_at).toLocaleString('zh-CN') : ''
  const esm = j.engine === 'esmfold2' ? formatEsmfoldParams(j.params_json as Record<string, number>) : ''
  return [engineLabel(j.engine), esm, chains && `${chains} aa`, created && `提交于 ${created}`]
    .filter(Boolean)
    .join(' · ')
})

async function loadDetail(silent = false) {
  if (!silent) loading.value = true
  try {
    job.value = await fetchJob(jobId.value)
    selectionStore.clearSequenceResidueSelection()
    try {
      const seqData = await fetchJobSequences(jobId.value)
      sequences.value = seqData.chains
    } catch {
      sequences.value = []
    }
  } catch (e) {
    job.value = null
    if (!silent) ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onStructureLoaded(payload: { jobId: string; cifText: string }) {
  cifText.value = payload.cifText
}

function goBack() {
  if (returnBatchId.value) {
    router.push({ name: 'fold-batch', params: { id: returnBatchId.value } })
  } else {
    router.push({ name: 'fold' })
  }
}

async function onDelete() {
  const j = job.value
  if (!j) return
  const label = j.name || j.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${label}」吗？\n\n将同时删除数据库记录和 outputs 目录中的结果文件，此操作不可恢复。`,
      '删除任务',
      { type: 'warning' },
    )
    await deleteJob(j.id)
    await foldStore.refreshFoldTasks()
    router.push({ name: 'fold' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function onDownload() {
  const j = job.value
  if (!j) return
  void downloadStructure(j.id, j.name || j.id)
}

function startMd() {
  const j = job.value
  if (!j) return
  router.push({ name: 'md', query: { parent: j.id } })
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

let pollHandle: ReturnType<typeof setInterval> | null = null

function setupPolling() {
  if (pollHandle) clearInterval(pollHandle)
  pollHandle = setInterval(async () => {
    if (!job.value || !['queued', 'running'].includes(job.value.status)) {
      if (pollHandle) clearInterval(pollHandle)
      pollHandle = null
      return
    }
    await loadDetail(true)
  }, 5000)
}

watch(jobId, () => {
  cifText.value = null
  void loadDetail()
  setupPolling()
})

watch(
  () => job.value?.status,
  (status) => {
    if (status && ['queued', 'running'].includes(status)) setupPolling()
  },
)

onMounted(async () => {
  await loadDetail()
  setupPolling()
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
          <div v-if="returnBatchId" class="back-link">
            <el-button size="small" text @click="goBack">← 返回批次</el-button>
          </div>
          <h2>{{ job.name || job.id }}</h2>
          <p class="detail-meta">{{ detailMeta }}</p>
        </div>
        <div class="detail-actions">
          <el-tag :type="statusTagType(job.status)" size="small">
            {{ statusLabel(job.status) }}
          </el-tag>
          <el-button v-if="job.status === 'done'" size="small" @click="onDownload">下载结构</el-button>
          <el-button
            v-if="job.status === 'done' && (job.engine === 'boltz2' || job.engine === 'esmfold2')"
            size="small"
            type="primary"
            plain
            @click="startMd"
          >
            启动 MD
          </el-button>
          <el-button size="small" type="danger" plain @click="onDelete">删除</el-button>
        </div>
      </div>

      <div v-if="job.error_message" class="error-box">{{ job.error_message }}</div>

      <MetricsGrid :items="metrics" />

      <StructureViewer
        :job-id="job.id"
        :status="job.status"
        :chains="interfaceChains"
        @loaded="onStructureLoaded"
      />

      <InterfacePanel
        :job-id="job.id"
        :status="job.status"
        :chain-count="chainCount"
        :cif-text="cifText"
      />

      <SequencePanel v-if="sequences.length" :chains="sequences" />
    </template>

    <el-empty v-else description="任务不存在或已删除" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
</style>
