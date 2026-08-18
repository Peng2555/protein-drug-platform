<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { api } from '@/api/client'
import {
  applyViewerStyles,
  createViewer,
  destroyViewer,
  load3DmolLib,
  resizeViewer,
} from '@/composables/use3Dmol'
import {
  applyPyMOLSelectionView,
  useSelectionStore,
} from '@/composables/useSelection'
import type { InterfaceChainMeta, Mol3DViewer, ViewerColorMode } from '@/types/structure'

export type { ViewerColorMode } from '@/types/structure'

const props = withDefaults(
  defineProps<{
    jobId?: string | null
    status?: string | null
    chains?: InterfaceChainMeta[] | null
    /** Pre-loaded mmCIF text; when omitted, fetched from API using jobId. */
    cifText?: string | null
  }>(),
  {
    jobId: null,
    status: null,
    chains: null,
    cifText: null,
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
const viewer = ref<Mol3DViewer | null>(null)
const colorMode = ref<ViewerColorMode>('chain')
const loading = ref(false)
const loadError = ref('')
const loadedJobId = ref<string | null>(null)
const internalCifText = ref<string | null>(null)
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

/** Overlay chrome (legend etc.) only after a successful mount. */
const showOverlay = computed(
  () => !loading.value && !loadError.value && !!viewer.value && !!loadedJobId.value,
)

/** Keep canvas mounted whenever we intend to show a done structure. */
const keepCanvas = computed(
  () => !!props.jobId && props.status === 'done',
)

function refreshViewerStyles(): void {
  const v = viewer.value
  if (!v) return
  v.removeAllLabels()
  if (selectedSeqResidues.value.size) {
    applyPyMOLSelectionView(v, colorMode.value, props.chains, selectionStore.getSelectedResiduesList())
  } else {
    applyViewerStyles(v, colorMode.value, props.chains)
  }
  resizeViewer(v)
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
  await load3DmolLib()
  await waitForVisibleCanvas()
  if (!viewerEl.value) return

  destroyViewer(viewer.value, viewerEl.value)
  viewer.value = createViewer(viewerEl.value, '0xeef2f7')
  viewer.value.addModel(text, 'cif')
  selectionStore.bindViewerResiduePick(viewer.value, (chainId, resi, event) => {
    emit('residue-click', { chainId, resi, event })
    refreshViewerStyles()
  })

  internalCifText.value = text
  loadedJobId.value = jobId
  refreshViewerStyles()
  viewer.value.zoomTo()
  resizeViewer(viewer.value)
  // One more frame after layout settles (avoids blank WebGL after route switch).
  await nextTick()
  requestAnimationFrame(() => resizeViewer(viewer.value))
  emit('loaded', { jobId, cifText: text })
}

async function loadStructure(): Promise<void> {
  const jobId = props.jobId
  if (!jobId || props.status !== 'done') {
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = null
    loadedJobId.value = null
    internalCifText.value = null
    loadError.value = ''
    loading.value = false
    return
  }

  if (loadedJobId.value === jobId && viewer.value) {
    refreshViewerStyles()
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
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = null
    emit('error', message)
  } finally {
    loading.value = false
    await nextTick()
    resizeViewer(viewer.value)
  }
}

function clearSelection(): void {
  selectionStore.clearSequenceResidueSelection()
  refreshViewerStyles()
}

function onColorModeChange(): void {
  refreshViewerStyles()
}

function onViewerResize(): void {
  resizeViewer(viewer.value)
}

watch(
  () => [props.jobId, props.status, props.cifText] as const,
  () => {
    void loadStructure()
  },
  { immediate: true },
)

watch(
  () => props.chains,
  () => refreshViewerStyles(),
  { deep: true },
)

watch(selectedSeqResidues, () => refreshViewerStyles(), { deep: true })

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined' && wrapEl.value) {
    resizeObserver = new ResizeObserver(() => onViewerResize())
    resizeObserver.observe(wrapEl.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  destroyViewer(viewer.value, viewerEl.value)
  viewer.value = null
})

defineExpose({
  refreshViewerStyles,
  getCifText: () => internalCifText.value,
  getViewer: () => viewer.value,
})
</script>

<template>
  <div class="structure-viewer">
    <div class="structure-viewer__head">
      <h3 class="structure-viewer__title">3D 结构</h3>
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
      <!-- Canvas stays laid out (not display:none) so WebGL gets a real size. -->
      <div
        v-show="keepCanvas"
        ref="viewerEl"
        class="structure-viewer__canvas"
        :class="{ 'is-ready': showOverlay }"
      />

      <div v-if="!showOverlay" v-loading="loading" class="structure-viewer__placeholder">
        <span>{{ placeholderMessage }}</span>
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
  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }

  &__title {
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--title);
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
    height: min(520px, 55vh);
    min-height: 360px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: linear-gradient(180deg, #eef2f7 0%, #e4eaf2 100%);
    overflow: hidden;

    &.is-loading {
      opacity: 0.95;
    }
  }

  &__canvas {
    width: 100%;
    height: 100%;
    cursor: crosshair;
    /* Stay in layout while loading so createViewer sees non-zero size. */
    visibility: hidden;

    &.is-ready {
      visibility: visible;
    }

    &:active {
      cursor: grabbing;
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
    background: linear-gradient(180deg, #eef2f7 0%, #e4eaf2 100%);
    z-index: 2;
  }
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
