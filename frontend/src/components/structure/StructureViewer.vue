<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '@/api/client'
import {
  applyMolstarChainPalette,
  applyMolstarColorMode,
  bindMolstarResiduePick,
  createMolstarViewer,
  destroyMolstarViewer,
  loadMolstarCif,
  resizeMolstarViewer,
  syncMolstarSelection,
  type MolstarViewer,
} from '@/composables/useMolstar'
import { useSelectionStore } from '@/composables/useSelection'
import type { InterfaceChainMeta, ViewerColorMode } from '@/types/structure'

export type { ViewerColorMode } from '@/types/structure'

const props = withDefaults(
  defineProps<{
    jobId?: string | null
    status?: string | null
    chains?: InterfaceChainMeta[] | null
    cifText?: string | null
    /** hero：嵌入详情主舞台，占满父容器高度 */
    variant?: 'default' | 'hero'
    /** 由外层 ComplexViewer 提供工具栏时隐藏内置标题区 */
    hideChrome?: boolean
  }>(),
  {
    jobId: null,
    status: null,
    chains: null,
    cifText: null,
    variant: 'default',
    hideChrome: false,
  },
)

const emit = defineEmits<{
  'residue-click': [payload: { chainId: string; resi: number; event: MouseEvent }]
  loaded: [payload: { jobId: string; cifText: string }]
  error: [message: string]
}>()

const selectionStore = useSelectionStore()
const { selectedSeqResidues } = storeToRefs(selectionStore)

const wrapEl = ref<HTMLElement | null>(null)
const viewerEl = ref<HTMLElement | null>(null)
const viewer = shallowRef<MolstarViewer | null>(null)
const colorMode = ref<ViewerColorMode>('chain')
const loading = ref(false)
const loadError = ref('')
const loadedJobId = ref<string | null>(null)
const internalCifText = ref<string | null>(null)
let pickUnsub: { unsubscribe: () => void } | null = null
let resizeObserver: ResizeObserver | null = null

const selectionCount = computed(() => selectedSeqResidues.value.size)

const placeholderMessage = computed(() => {
  if (loadError.value) return loadError.value
  if (loading.value) return '正在加载 3D 结构…'
  if (props.status === 'queued') return '任务排队中，完成后将自动显示 3D 结构…'
  if (props.status === 'running') return '结构预测进行中，请稍候…'
  if (props.status === 'failed') return '预测失败，无结构可显示'
  if (!props.jobId) return '暂无 3D 结构'
  if (props.status && props.status !== 'done') return '暂无 3D 结构'
  return '暂无 3D 结构'
})

const showOverlay = computed(
  () => !loading.value && !loadError.value && !!viewer.value && !!loadedJobId.value,
)

const keepCanvas = computed(
  () => !!props.jobId && props.status === 'done',
)

async function refreshViewerStyles(): Promise<void> {
  const v = viewer.value
  if (!v) return
  if (colorMode.value === 'chain' && props.chains?.length) {
    await applyMolstarChainPalette(v, props.chains)
  } else {
    await applyMolstarColorMode(v, colorMode.value)
  }
  syncMolstarSelection(v, selectionStore.getSelectedResiduesList())
  resizeMolstarViewer(v)
}

async function fetchStructureText(jobId: string): Promise<string> {
  const resp = await api.get<string>(`/api/jobs/${jobId}/structure`, {
    responseType: 'text',
    transformResponse: [(data) => data],
  })
  return resp.data
}

async function waitForVisibleCanvas(maxFrames = 30): Promise<boolean> {
  for (let i = 0; i < maxFrames; i += 1) {
    await nextTick()
    const el = viewerEl.value
    if (el && el.clientWidth > 0 && el.clientHeight > 0) return true
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  }
  return !!(viewerEl.value && viewerEl.value.clientWidth > 0 && viewerEl.value.clientHeight > 0)
}

async function mountStructure(jobId: string, text: string): Promise<void> {
  await waitForVisibleCanvas()
  if (!viewerEl.value) return

  pickUnsub?.unsubscribe()
  pickUnsub = null
  destroyMolstarViewer(viewer.value, viewerEl.value)
  selectionStore.detachViewer()

  const v = await createMolstarViewer(viewerEl.value)
  viewer.value = v
  await loadMolstarCif(v, text)
  pickUnsub = bindMolstarResiduePick(v, (chainId, resi, event) => {
    selectionStore.selectSequenceResidue(chainId, resi, event)
    emit('residue-click', { chainId, resi, event: event as MouseEvent })
    void refreshViewerStyles()
  })

  internalCifText.value = text
  loadedJobId.value = jobId
  await refreshViewerStyles()
  await nextTick()
  requestAnimationFrame(() => resizeMolstarViewer(v))
  emit('loaded', { jobId, cifText: text })
}

async function loadStructure(): Promise<void> {
  const jobId = props.jobId
  if (!jobId || props.status !== 'done') {
    pickUnsub?.unsubscribe()
    pickUnsub = null
    destroyMolstarViewer(viewer.value, viewerEl.value)
    viewer.value = null
    selectionStore.detachViewer()
    loadedJobId.value = null
    internalCifText.value = null
    loadError.value = ''
    loading.value = false
    return
  }

  if (loadedJobId.value === jobId && viewer.value) {
    await refreshViewerStyles()
    return
  }

  loading.value = true
  loadError.value = ''
  try {
    const text = props.cifText ?? (await fetchStructureText(jobId))
    await mountStructure(jobId, text)
  } catch (e) {
    const message = e instanceof Error ? e.message : '3D 加载失败'
    loadError.value = message
    loadedJobId.value = null
    internalCifText.value = null
    destroyMolstarViewer(viewer.value, viewerEl.value)
    viewer.value = null
    emit('error', message)
  } finally {
    loading.value = false
    await nextTick()
    resizeMolstarViewer(viewer.value)
  }
}

function clearSelection(): void {
  selectionStore.clearSequenceResidueSelection()
}

function onColorModeChange(): void {
  void refreshViewerStyles()
}

function onViewerResize(): void {
  resizeMolstarViewer(viewer.value)
}

function retryLoad(): void {
  loadedJobId.value = null
  loadError.value = ''
  void loadStructure()
}

watch(
  () => [props.jobId, props.status, props.cifText] as const,
  () => { void loadStructure() },
  { immediate: true },
)

watch(colorMode, () => {
  void refreshViewerStyles()
})

watch(
  () => props.chains,
  () => { void refreshViewerStyles() },
  { deep: true },
)

watch(selectedSeqResidues, () => {
  if (viewer.value) syncMolstarSelection(viewer.value, selectionStore.getSelectedResiduesList())
}, { deep: true })

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined' && wrapEl.value) {
    resizeObserver = new ResizeObserver(() => onViewerResize())
    resizeObserver.observe(wrapEl.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  pickUnsub?.unsubscribe()
  destroyMolstarViewer(viewer.value, viewerEl.value)
  viewer.value = null
  selectionStore.detachViewer()
})

defineExpose({
  refreshViewerStyles,
  getCifText: () => internalCifText.value,
  getViewer: () => viewer.value,
  retryLoad,
  setColorMode: (mode: ViewerColorMode) => {
    colorMode.value = mode
    void refreshViewerStyles()
  },
})
</script>

<template>
  <div class="structure-viewer" :class="{ 'structure-viewer--hero': variant === 'hero' }">
    <div v-if="!hideChrome" class="structure-viewer__head">
      <div class="structure-viewer__titles">
        <h3 class="structure-viewer__title">3D 结构</h3>
        <p v-if="variant !== 'hero'" class="structure-viewer__hint">Mol* 渲染 · 高质量 cartoon</p>
      </div>
      <div class="structure-viewer__actions">
        <span v-if="selectionCount > 0" class="structure-viewer__sel-count">
          已选 {{ selectionCount }} 个残基
        </span>
        <el-button
          v-if="selectionCount > 0"
          size="small"
          plain
          @click="clearSelection"
        >
          清除选中
        </el-button>
        <el-select
          v-model="colorMode"
          size="small"
          class="structure-viewer__mode"
          @change="onColorModeChange"
        >
          <el-option label="按链着色" value="chain" />
          <el-option label="pLDDT" value="plddt" />
        </el-select>
      </div>
    </div>

    <div ref="wrapEl" class="structure-viewer__wrap" :class="{ 'is-loading': loading }">
      <div
        v-show="keepCanvas"
        ref="viewerEl"
        class="structure-viewer__canvas molstar-viewer-host"
        :class="{ 'is-ready': showOverlay }"
      />

      <div
        v-if="!showOverlay"
        v-loading="loading"
        class="structure-viewer__placeholder"
      >
        <div class="structure-viewer__placeholder-inner">
          <span>{{ placeholderMessage }}</span>
          <el-button
            v-if="loadError && jobId && status === 'done'"
            type="primary"
            size="small"
            class="structure-viewer__retry"
            @click="retryLoad"
          >
            重试加载
          </el-button>
        </div>
      </div>

      <div v-if="showOverlay && colorMode === 'plddt'" class="plddt-overlay">
        <div class="plddt-overlay-title">pLDDT</div>
        <div class="plddt-af-legend">
          <div class="plddt-af-item">
            <span class="plddt-af-bar plddt-high" />
            <span class="plddt-af-label">&gt;90</span>
          </div>
          <div class="plddt-af-item">
            <span class="plddt-af-bar plddt-good" />
            <span class="plddt-af-label">70–90</span>
          </div>
          <div class="plddt-af-item">
            <span class="plddt-af-bar plddt-low" />
            <span class="plddt-af-label">50–70</span>
          </div>
          <div class="plddt-af-item">
            <span class="plddt-af-bar plddt-poor" />
            <span class="plddt-af-label">&lt;50</span>
          </div>
        </div>
      </div>

      <div
        v-if="showOverlay && colorMode === 'chain' && props.chains?.length"
        class="chain-legend"
      >
        <div class="chain-legend-title">链标注</div>
        <div
          v-for="ch in props.chains"
          :key="ch.chain_id"
          class="chain-legend-item"
        >
          <span class="chain-legend-swatch" :style="{ background: ch.color }" />
          <span>{{ ch.label }} · {{ ch.length }} aa</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.structure-viewer {
  &--hero {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;

    .structure-viewer__head {
      margin-bottom: 0.55rem;
      flex-shrink: 0;
    }

    .structure-viewer__wrap {
      flex: 1;
      height: auto;
      min-height: 0;
      border-radius: 12px;
    }
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }

  &__titles {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  &__title {
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--title);
  }

  &__hint {
    margin: 0;
    font-size: 0.72rem;
    color: var(--muted);
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  &__sel-count {
    font-size: 0.78rem;
    color: var(--muted);
  }

  &__mode {
    width: 120px;
  }

  &__wrap {
    position: relative;
    height: min(720px, 72vh);
    min-height: 520px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: #f1f5f9;
    overflow: hidden;

    &.is-loading {
      opacity: 0.95;
    }
  }

  &__canvas {
    width: 100%;
    height: 100%;
    opacity: 0;
    transition: opacity 0.15s ease;

    &.is-ready {
      opacity: 1;
    }
  }

  &__placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 1rem;
    text-align: center;
    font-size: 0.88rem;
    color: var(--muted);
    background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
    z-index: 2;
  }

  &__placeholder-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    max-width: 28rem;
  }

  &__retry {
    margin-top: 0.15rem;
  }
}

.molstar-viewer-host :deep(.msp-plugin) {
  width: 100%;
  height: 100%;
}

.plddt-overlay {
  position: absolute;
  right: 12px;
  top: 12px;
  z-index: 10;
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  border: 1px solid rgba(203, 213, 225, 0.9);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  pointer-events: none;
}

.plddt-overlay-title {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.35rem;
}

.plddt-af-legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.35rem 0.6rem;
}

.plddt-af-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.plddt-af-bar {
  width: 28px;
  height: 8px;
  border-radius: 2px;
}

.plddt-af-label {
  font-size: 0.68rem;
  color: var(--body);
}

.plddt-high { background: #0053d6; }
.plddt-good { background: #00c1f2; }
.plddt-low { background: #fffd00; }
.plddt-poor { background: #ff7d00; }

.chain-legend {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 10;
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  border: 1px solid rgba(203, 213, 225, 0.9);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  font-size: 0.72rem;
  color: var(--body);
  pointer-events: none;
}

.chain-legend-title {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.35rem;
}

.chain-legend-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.15rem 0;
}

.chain-legend-swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  border: 1px solid rgba(15, 23, 42, 0.08);
}
</style>
