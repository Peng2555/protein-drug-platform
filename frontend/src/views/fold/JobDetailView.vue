<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteJob, downloadStructure, fetchJob } from '@/api/jobs'
import { fetchJobSequences } from '@/api/sequences'
import ComplexViewer from '@/components/fold/ComplexViewer.vue'
import FoldHeader from '@/components/fold/FoldHeader.vue'
import QualityMetricCards from '@/components/fold/QualityMetricCards.vue'
import InterfacePanel from '@/components/structure/InterfacePanel.vue'
import { useSelectionStore } from '@/composables/useSelection'
import { useFoldTasksStore } from '@/stores/foldTasks'
import type { Job, ChainSequence } from '@/api/types'
import type { InterfaceChainMeta, InterfaceInteraction, JobInterfaceData } from '@/types/structure'
import { metricLevel, type FoldComplexInfo, type FoldScoreCard } from '@/types/foldWorkbench'
import { engineLabel, formatEsmfoldParams, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const foldStore = useFoldTasksStore()
const selectionStore = useSelectionStore()

const loading = ref(true)
const job = ref<Job | null>(null)
const sequences = ref<ChainSequence[]>([])
const cifText = ref<string | null>(null)
const interfaceData = ref<JobInterfaceData | null>(null)
const complexRef = ref<InstanceType<typeof ComplexViewer> | null>(null)
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

const metaTags = computed(() => {
  const j = job.value
  if (!j) return []
  const tags: string[] = [`模型: ${engineLabel(j.engine)}`]
  if (j.total_length) tags.push(`总长: ${j.total_length} aa`)
  const chains = Object.entries(j.chains_json || {})
  if (chains.length) tags.push(`链: ${chains.map(([k, v]) => `${k}(${v})`).join(' · ')}`)
  if (j.engine === 'esmfold2') {
    const esm = formatEsmfoldParams(j.params_json as Record<string, number>)
    if (esm) tags.push(esm)
  }
  return tags
})

const scoreCards = computed((): FoldScoreCard[] => {
  const j = job.value
  if (!j) return []
  const ix = interfaceData.value?.primary_interface
  const ixTotal = ix?.interaction_summary?.n_total ?? ix?.interactions?.length ?? null
  return [
    {
      key: 'iptm',
      label: 'ipTM',
      value: j.iptm != null ? j.iptm.toFixed(3) : '—',
      hint: '复合物界面置信度',
      tone: 'primary',
      level: metricLevel(j.iptm, 'iptm'),
    },
    {
      key: 'plddt',
      label: 'pLDDT',
      value: j.complex_plddt != null ? formatPlddt(j.complex_plddt) : '—',
      hint: '整体结构置信度',
      tone: 'ok',
      level: metricLevel(j.complex_plddt, 'plddt'),
    },
    {
      key: 'pdockq',
      label: 'pDockQ',
      value: j.pdockq != null ? j.pdockq.toFixed(3) : '—',
      hint: j.pdockq2 != null ? `pDockQ2 ${j.pdockq2.toFixed(3)}` : '界面质量评分',
      tone: 'warn',
      level: metricLevel(j.pdockq, 'pdockq'),
    },
    {
      key: 'conf',
      label: '置信度',
      value: j.confidence_score != null ? j.confidence_score.toFixed(3) : '—',
      hint: ixTotal != null ? `相互作用 ${ixTotal} 条` : '结构整体置信度',
      tone: 'info',
      level: metricLevel(j.confidence_score ?? j.iptm, 'iptm'),
    },
  ]
})

const complexInfo = computed((): FoldComplexInfo | null => {
  const j = job.value
  if (!j) return null
  const antibody = (interfaceChains.value || [])
    .filter((c) => c.is_antibody)
    .map((c) => c.label)
    .join(' · ')
  const antigen = (interfaceChains.value || [])
    .filter((c) => !c.is_antibody)
    .map((c) => c.label)
    .join(' · ')
  return {
    antibodyChains: antibody || '—',
    antigenChains: antigen || '—',
    ligand: '无 / 未标注',
    totalResidues: j.total_length,
    model: engineLabel(j.engine),
    predictedAt: j.finished_at
      ? new Date(j.finished_at).toLocaleString('zh-CN')
      : j.created_at
        ? new Date(j.created_at).toLocaleString('zh-CN')
        : '—',
  }
})

const finishedText = computed(() => {
  const j = job.value
  if (!j?.finished_at) return ''
  return `完成于 ${new Date(j.finished_at).toLocaleString('zh-CN')}`
})

function formatPlddt(v: number): string {
  const score = v <= 1.5 ? v * 100 : v
  return score.toFixed(1)
}

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

function onInterfaceLoaded(data: JobInterfaceData) {
  interfaceData.value = data
}

function onFocusInteraction(ix: InterfaceInteraction) {
  // 主复合物 3D 同步聚焦（界面面板自身也会聚焦其 viewer）
  complexRef.value?.focusInteraction(ix)
}

function goBack() {
  if (returnBatchId.value) {
    router.push({ name: 'fold-batch', params: { id: returnBatchId.value } })
  } else {
    router.push({ name: 'fold-tasks' })
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
    router.push({ name: 'fold-new' })
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
  router.push({ name: 'md-new', query: { parent: j.id } })
}

function startDesign() {
  const j = job.value
  if (!j) return
  router.push({ name: 'design-new', query: { fold_job: j.id } })
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
  interfaceData.value = null
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
  <div v-loading="loading" class="fold-job">
    <template v-if="job">
      <FoldHeader
        :title="job.name || job.id"
        :crumb-parent="returnBatchId ? '返回批次' : '结构预测'"
        :status-label="statusLabel(job.status)"
        :status-type="statusTagType(job.status)"
        :finished-text="finishedText"
        :tags="metaTags"
        :show-md="job.status === 'done' && (job.engine === 'boltz2' || job.engine === 'esmfold2')"
        :show-design="job.status === 'done' && (job.engine === 'boltz2' || job.engine === 'esmfold2')"
        :show-export="job.status === 'done'"
        @back="goBack"
        @start-md="startMd"
        @start-design="startDesign"
        @export="onDownload"
        @delete="onDelete"
      />

      <div v-if="job.error_message" class="error-box">{{ job.error_message }}</div>

      <div class="fold-job__body">
        <ComplexViewer
          ref="complexRef"
          :job-id="job.id"
          :status="job.status"
          :chains="interfaceChains"
          :sequences="sequences"
          @loaded="onStructureLoaded"
        />

        <aside class="fold-job__rail">
          <section class="rail-block page-card">
            <h3>预测质量</h3>
            <QualityMetricCards :cards="scoreCards" />
          </section>

          <section v-if="complexInfo" class="rail-block page-card">
            <h3>复合物信息</h3>
            <dl class="info-grid">
              <div><dt>抗体链</dt><dd>{{ complexInfo.antibodyChains }}</dd></div>
              <div><dt>抗原链</dt><dd>{{ complexInfo.antigenChains }}</dd></div>
              <div><dt>配体</dt><dd>{{ complexInfo.ligand }}</dd></div>
              <div><dt>总残基数</dt><dd>{{ complexInfo.totalResidues ?? '—' }}</dd></div>
              <div><dt>模型</dt><dd>{{ complexInfo.model }}</dd></div>
              <div><dt>预测时间</dt><dd>{{ complexInfo.predictedAt }}</dd></div>
            </dl>
          </section>
        </aside>
      </div>

      <!-- 完整结合界面：含界面 3D、相互作用表、界面残基 -->
      <InterfacePanel
        :job-id="job.id"
        :chain-count="chainCount"
        :cif-text="cifText"
        @loaded="onInterfaceLoaded"
        @focus-interaction="onFocusInteraction"
      />
    </template>

    <el-empty v-else description="任务不存在或已删除" />
  </div>
</template>

<style scoped lang="scss">
.fold-job {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-height: calc(100vh - var(--app-topbar-height) - 40px);
}

.fold-job__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 340px);
  gap: 0.85rem;
  align-items: stretch;
  min-height: min(640px, 68vh);

  @media (max-width: 1280px) {
    grid-template-columns: 1fr;
    min-height: 0;
  }
}

.fold-job__rail {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
  min-width: 0;
  min-height: 0;
  max-height: min(720px, 70vh);
  overflow: auto;
}

.rail-block {
  padding: 0.8rem 0.85rem;
  flex-shrink: 0;

  h3 {
    margin: 0 0 0.65rem;
    font-size: 0.86rem;
    color: var(--title);
  }
}

.info-grid {
  margin: 0;
  display: grid;
  gap: 0.45rem;

  div {
    display: grid;
    grid-template-columns: 72px 1fr;
    gap: 0.4rem;
    font-size: 0.78rem;
  }

  dt {
    color: var(--muted);
  }

  dd {
    margin: 0;
    color: var(--body);
    font-weight: 600;
  }
}

.error-box {
  margin: 0;
  padding: 0.65rem 0.85rem;
  border-radius: var(--radius-sm);
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 0.85rem;
  white-space: pre-wrap;
}
</style>
