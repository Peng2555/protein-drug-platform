<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import SequenceStrip from '@/components/sequence/SequenceStrip.vue'
import { fetchJob, fetchStructureText } from '@/api/jobs'
import type { Job } from '@/api/types'
import type { AntibodyVersion } from '@/api/antibodyProjects'
import { usePolling } from '@/composables/usePolling'
import { useSelectionStore } from '@/composables/useSelection'
import {
  applyMolstarMutationTheme,
  clearMolstarPlugin,
  createMolstarViewer,
  destroyMolstarViewer,
  focusMolstarResidues,
  loadMolstarStructure,
  resizeMolstarViewer,
  superposeMolstarMobileOntoPivot,
  type MolstarViewer,
} from '@/composables/useMolstar'
import {
  cdrResidueKeys,
  mutationResidueKeys,
  versionToFoldSequences,
} from '@/utils/antibodyFoldView'
import { statusLabel } from '@/utils/constants'

const props = defineProps<{
  version: AntibodyVersion
  parentVersion?: AntibodyVersion | null
  jobId: string
  parentJobId?: string | null
}>()

const router = useRouter()
const selectionStore = useSelectionStore()
const wrapEl = ref<HTMLElement | null>(null)
const viewerEl = ref<HTMLElement | null>(null)
const viewer = shallowRef<MolstarViewer | null>(null)
const job = ref<Job | null>(null)
const parentJob = ref<Job | null>(null)
const overlay = ref(true)
const loading = ref(false)
const loadError = ref('')
const rmsdText = ref('')
const loaded = ref(false)
let resizeObserver: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

const sequences = computed(() => versionToFoldSequences(props.version))
const mutatedKeys = computed(() => mutationResidueKeys(props.version.mutations))
const jobDone = computed(() => job.value?.status === 'done')
const parentDone = computed(() => parentJob.value?.status === 'done')
const canOverlay = computed(() => Boolean(props.parentJobId && parentDone.value && props.parentVersion))
const pollJobs = computed(() => {
  if (!props.jobId) return false
  if (!jobDone.value) return true
  if (props.parentJobId && !parentDone.value) return true
  return false
})

async function refreshJobs() {
  if (!props.jobId) return
  try {
    job.value = await fetchJob(props.jobId)
    if (props.parentJobId) {
      parentJob.value = await fetchJob(props.parentJobId)
    } else {
      parentJob.value = null
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '任务状态加载失败'
  }
}

usePolling(refreshJobs, pollJobs, { interval: 5000 })

function fitViewer() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (viewer.value) resizeMolstarViewer(viewer.value)
  }, 80)
}

async function applyMutationLook(v: MolstarViewer) {
  await applyMolstarMutationTheme(v, mutatedKeys.value)
}

async function mountViewer() {
  loaded.value = false
  loadError.value = ''
  rmsdText.value = ''
  if (!jobDone.value || !viewerEl.value) {
    destroyMolstarViewer(viewer.value, viewerEl.value)
    viewer.value = null
    selectionStore.detachViewer()
    selectionStore.clearSequenceResidueSelection()
    return
  }
  loading.value = true
  try {
    const mutantCif = await fetchStructureText(props.jobId)
    const showOverlay = overlay.value && canOverlay.value && props.parentJobId
    const parentCif = showOverlay ? await fetchStructureText(props.parentJobId!) : null
    await nextTick()
    if (!viewerEl.value) return
    destroyMolstarViewer(viewer.value, viewerEl.value)
    selectionStore.detachViewer()
    const v = await createMolstarViewer(viewerEl.value)
    viewer.value = v
    await clearMolstarPlugin(v)
    await loadMolstarStructure(v, mutantCif, undefined, {
      resetCamera: !parentCif,
      dataLabel: 'mutant',
      preset: 'polymer-cartoon',
    })
    if (parentCif) {
      await loadMolstarStructure(v, parentCif, undefined, {
        resetCamera: false,
        dataLabel: 'parent',
        preset: 'polymer-cartoon',
      })
      const fit = await superposeMolstarMobileOntoPivot(v, cdrResidueKeys(props.version))
      rmsdText.value = fit
        ? `骨架叠合 RMSD ${fit.rmsd.toFixed(2)} Å · ${fit.n} 个 FR Cα`
        : '母本已加载，但骨架原子太少，未能叠合'
    }
    selectionStore.bindViewerResiduePick(v, (chainId, resi) => {
      focusMolstarResidues(v, [{ chain_id: chainId, seq_num: resi }])
    })
    await applyMutationLook(v)
    loaded.value = true
    requestAnimationFrame(fitViewer)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '结构加载失败'
  } finally {
    loading.value = false
  }
}

function onResidueClick(payload: { chainId: string; resi: number }) {
  const v = viewer.value
  if (!v) return
  focusMolstarResidues(v, [{ chain_id: payload.chainId, seq_num: payload.resi }])
}

watch(
  () => [props.jobId, props.parentJobId, jobDone.value, canOverlay.value, overlay.value] as const,
  () => { void mountViewer() },
)

watch(
  () => wrapEl.value,
  (el) => {
    resizeObserver?.disconnect()
    if (!el) return
    resizeObserver = new ResizeObserver(fitViewer)
    resizeObserver.observe(el)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeObserver?.disconnect()
  destroyMolstarViewer(viewer.value, viewerEl.value)
  selectionStore.detachViewer()
})
</script>

<template>
  <div class="version-structure">
    <div class="toolbar">
      <div class="toolbar-copy">
        <strong>抗体自身结构</strong>
        <p>
          红色为相对父本的突变。点序列可对准三维。
          <template v-if="canOverlay">叠母本时按 FR 骨架对齐，CDR 差别会留下来。</template>
        </p>
        <p v-if="rmsdText" class="rmsd">{{ rmsdText }}</p>
      </div>
      <div class="toolbar-actions">
        <el-switch
          v-if="canOverlay"
          v-model="overlay"
          active-text="叠母本"
          inactive-text="只看本版"
        />
        <el-button text type="primary" @click="router.push({ name: 'fold-task', params: { id: jobId } })">
          打开折叠作业
        </el-button>
      </div>
    </div>

    <div v-if="job && job.status !== 'done'" class="status-note">
      折叠{{ statusLabel(job.status) }}{{ job.error_message ? `：${job.error_message}` : '，完成后会自动出现结构。' }}
    </div>

    <div ref="wrapEl" class="stage">
      <div ref="viewerEl" class="canvas molstar-viewer-host" />
      <div v-if="loading || loadError || !jobDone" class="mask">
        {{ loadError || (loading ? '正在加载结构…' : job ? `等待折叠${statusLabel(job.status)}` : '暂无结构') }}
      </div>
    </div>

    <SequenceStrip
      v-if="jobDone && sequences.length"
      :chains="sequences"
      :mutated-keys="mutatedKeys"
      @residue-click="onResidueClick"
    />
  </div>
</template>

<style scoped lang="scss">
.version-structure {
  display: grid;
  gap: 0.65rem;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: flex-start;
}
.toolbar-copy {
  min-width: 0;
  strong { color: var(--title); }
  p { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.82rem; }
  .rmsd { color: var(--body); }
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-shrink: 0;
}
.status-note {
  color: var(--muted);
  font-size: 0.85rem;
}
.stage {
  position: relative;
  height: 460px;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: #eef2f6;
}
.canvas { width: 100%; height: 100%; }
.mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(248, 250, 252, 0.72);
  color: var(--muted);
  font-size: 0.9rem;
  z-index: 2;
}
</style>
