<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import StructureViewer from '@/components/structure/StructureViewer.vue'
import SequenceStrip from '@/components/sequence/SequenceStrip.vue'
import {
  applyMolstarColorMode,
  focusMolstarPoint,
  focusMolstarResidues,
  highlightMolstarResidues,
  resizeMolstarViewer,
  type MolstarViewer,
} from '@/composables/useMolstar'
import type { ChainSequence } from '@/api/types'
import type { InterfaceChainMeta, InterfaceInteraction, ViewerColorMode } from '@/types/structure'

const props = withDefaults(
  defineProps<{
    jobId?: string | null
    status?: string | null
    chains?: InterfaceChainMeta[] | null
    sequences?: ChainSequence[] | null
  }>(),
  {
    jobId: null,
    status: null,
    chains: null,
    sequences: null,
  },
)

const emit = defineEmits<{
  loaded: [payload: { jobId: string; cifText: string }]
  error: [message: string]
}>()

const viewerRef = ref<InstanceType<typeof StructureViewer> | null>(null)
const colorMode = ref<ViewerColorMode>('chain')
const fullscreen = ref(false)
const showSequence = ref(true)
const shellEl = ref<HTMLElement | null>(null)

const hasSequences = computed(() => (props.sequences?.length || 0) > 0)

const webglOk = computed(() => {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
})

function getViewer(): MolstarViewer | null {
  return viewerRef.value?.getViewer?.() ?? null
}

async function setColorMode(mode: ViewerColorMode) {
  colorMode.value = mode
  const sv = viewerRef.value
  if (sv?.setColorMode) {
    sv.setColorMode(mode)
    return
  }
  const v = getViewer()
  if (!v) return
  await applyMolstarColorMode(v, mode)
}

function captureScreenshot() {
  const v = getViewer()
  const canvas = v?.plugin.canvas3d?.webgl?.gl?.canvas as HTMLCanvasElement | undefined
  if (!canvas) return
  try {
    const url = canvas.toDataURL('image/png')
    const a = document.createElement('a')
    a.href = url
    a.download = `structure-${props.jobId || 'snapshot'}.png`
    a.click()
  } catch {
    /* ignore */
  }
}

function retryStructure() {
  viewerRef.value?.retryLoad?.()
}

function resetCamera() {
  const v = getViewer()
  v?.plugin.canvas3d?.requestCameraReset()
}

function zoom(factor: number) {
  const v = getViewer()
  const cam = v?.plugin.canvas3d?.camera
  if (!cam) return
  try {
    const snapshot = cam.getSnapshot()
    const next = {
      ...snapshot,
      radius: Math.max(2, (snapshot.radius || 20) * factor),
    }
    cam.setState(next, 180)
  } catch {
    /* ignore */
  }
}

function focusInteraction(ix: InterfaceInteraction) {
  const v = getViewer()
  if (!v) return
  const residues = [
    { chain_id: ix.chain_a, seq_num: ix.resnum_a },
    { chain_id: ix.chain_b, seq_num: ix.resnum_b },
  ]
  highlightMolstarResidues(v, residues, 'highlight')
  focusMolstarResidues(v, residues)
  if (ix.coord_a?.length >= 3 && ix.coord_b?.length >= 3) {
    focusMolstarPoint(v, {
      x: (ix.coord_a[0] + ix.coord_b[0]) / 2,
      y: (ix.coord_a[1] + ix.coord_b[1]) / 2,
      z: (ix.coord_a[2] + ix.coord_b[2]) / 2,
    })
  }
}

function focusInterfaceResidues(residues: Array<{ chain_id: string; seq_num: number }>) {
  const v = getViewer()
  if (!v || !residues.length) return
  highlightMolstarResidues(v, residues, 'highlight')
  focusMolstarResidues(v, residues)
}

async function toggleFullscreen() {
  const el = shellEl.value
  if (!el) return
  if (!document.fullscreenElement) {
    await el.requestFullscreen?.()
    fullscreen.value = true
  } else {
    await document.exitFullscreen?.()
    fullscreen.value = false
  }
  await nextTick()
  resizeMolstarViewer(getViewer())
}

function onLoaded(payload: { jobId: string; cifText: string }) {
  emit('loaded', payload)
  requestAnimationFrame(() => resizeMolstarViewer(getViewer()))
}

function onError(message: string) {
  emit('error', message)
}

async function toggleSequence() {
  showSequence.value = !showSequence.value
  await nextTick()
  resizeMolstarViewer(getViewer())
}

watch(fullscreen, async () => {
  await nextTick()
  resizeMolstarViewer(getViewer())
})

watch(showSequence, async () => {
  await nextTick()
  resizeMolstarViewer(getViewer())
})

defineExpose({
  focusInteraction,
  focusInterfaceResidues,
  setColorMode,
  resetCamera,
  getViewer,
})
</script>

<template>
  <section ref="shellEl" class="complex-viewer page-card">
    <div class="complex-viewer__toolbar">
      <div class="toolbar-left">
        <strong>复合物 3D</strong>
        <span>Mol* · 真实结构</span>
      </div>
      <div class="toolbar-actions">
        <el-button-group size="small">
          <el-button @click="resetCamera">重置视角</el-button>
          <el-button @click="zoom(0.85)">放大</el-button>
          <el-button @click="zoom(1.18)">缩小</el-button>
        </el-button-group>
        <el-button-group size="small">
          <el-button
            :type="colorMode === 'chain' ? 'primary' : 'default'"
            @click="setColorMode('chain')"
          >
            按链着色
          </el-button>
          <el-button
            :type="colorMode === 'plddt' ? 'primary' : 'default'"
            @click="setColorMode('plddt')"
          >
            pLDDT
          </el-button>
        </el-button-group>
        <el-button
          v-if="hasSequences"
          size="small"
          :type="showSequence ? 'primary' : 'default'"
          @click="toggleSequence"
        >
          序列
        </el-button>
        <el-button size="small" @click="captureScreenshot">截图</el-button>
        <el-button size="small" @click="toggleFullscreen">
          {{ fullscreen ? '退出全屏' : '全屏' }}
        </el-button>
        <el-button size="small" @click="retryStructure">重试</el-button>
      </div>
    </div>

    <el-alert
      v-if="!webglOk"
      type="error"
      :closable="false"
      show-icon
      title="当前浏览器不支持 WebGL，无法渲染 3D 结构。请更换 Chrome / Edge / Firefox 最新版。"
      class="complex-viewer__alert"
    />

    <div class="complex-viewer__body">
      <div class="complex-viewer__stage">
        <StructureViewer
          ref="viewerRef"
          variant="hero"
          hide-chrome
          :job-id="jobId"
          :status="status"
          :chains="chains"
          @loaded="onLoaded"
          @error="onError"
        />
      </div>

      <SequenceStrip
        v-if="hasSequences && showSequence"
        :chains="sequences || []"
      />
    </div>
  </section>
</template>

<style scoped lang="scss">
.complex-viewer {
  height: 100%;
  min-height: min(640px, 68vh);
  display: flex;
  flex-direction: column;
  padding: 0.7rem 0.8rem 0;
  background: linear-gradient(180deg, #eef3f7 0%, #f8fafc 40%, #fff 100%);
  overflow: hidden;
}

.complex-viewer__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.55rem;
  flex-shrink: 0;
  padding-right: 0.1rem;
}

.toolbar-left {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;

  strong {
    font-size: 0.9rem;
    color: var(--title);
  }

  span {
    font-size: 0.7rem;
    color: var(--muted);
  }
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
}

.complex-viewer__alert {
  margin-bottom: 0.55rem;
  flex-shrink: 0;
}

.complex-viewer__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 10px 10px 0 0;
  overflow: hidden;
}

.complex-viewer__stage {
  flex: 1;
  min-height: 360px;
}
</style>
