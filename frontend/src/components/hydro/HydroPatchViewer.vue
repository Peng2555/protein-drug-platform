<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  applyMolstarColorMode,
  applyMolstarHydroPatchTheme,
  applyMolstarStructurePreset,
  bindMolstarResiduePick,
  createMolstarViewer,
  destroyMolstarViewer,
  focusMolstarResidues,
  highlightMolstarResidues,
  loadMolstarCif,
  resizeMolstarViewer,
  type MolstarReprKind,
  type MolstarViewer,
} from '@/composables/useMolstar'
import type { ViewerColorMode } from '@/types/structure'
import {
  hydroColorByResidue,
  patchResidueItems,
  residueKey,
  type HydroPatch,
  type HydroResidue,
} from '@/utils/hydroPatches'

const props = withDefaults(
  defineProps<{
    cifText: string | null
    residues: HydroResidue[]
    patches: HydroPatch[]
    selectedPatchId?: string | null
    selectedResidue?: { chainId: string; resi: number } | null
    patchColorLabel?: string
  }>(),
  {
    cifText: null,
    residues: () => [],
    patches: () => [],
    selectedPatchId: null,
    selectedResidue: null,
    patchColorLabel: '疏水斑',
  },
)

const emit = defineEmits<{
  'select-patch': [patchId: string | null]
  'residue-click': [payload: { chainId: string; resi: number }]
}>()

const wrapEl = ref<HTMLElement | null>(null)
const viewerEl = ref<HTMLElement | null>(null)
const viewer = shallowRef<MolstarViewer | null>(null)
const colorMode = ref<ViewerColorMode>('hydro-patch')
const reprKind = ref<MolstarReprKind>('molecular-surface')
const loading = ref(false)
const reprBusy = ref(false)
const loadError = ref('')
const loaded = ref(false)
let appliedRepr: MolstarReprKind | null = null
let pickUnsub: { unsubscribe: () => void } | null = null
let resizeObserver: ResizeObserver | null = null
let lastSize = { w: 0, h: 0 }
let applying = false
let resizeTimer: ReturnType<typeof setTimeout> | null = null

function fitViewer() {
  const el = wrapEl.value
  const v = viewer.value
  if (!el || !v) return
  const w = Math.round(el.clientWidth)
  const h = Math.round(el.clientHeight)
  if (w < 8 || h < 8) return
  if (w === lastSize.w && h === lastSize.h) return
  lastSize = { w, h }
  resizeMolstarViewer(v)
}

function scheduleFit() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(fitViewer, 80)
}

const residuePatch = computed(() => {
  const m = new Map<string, string>()
  for (const r of props.residues) {
    if (r.patch_id) m.set(residueKey(r.chain, r.position), r.patch_id)
  }
  return m
})

const residueColors = computed(() => hydroColorByResidue(props.residues, props.patches))

const selectedPatch = computed(
  () => props.patches.find((p) => p.patch_id === props.selectedPatchId) ?? null,
)

async function applyTheme(): Promise<void> {
  const v = viewer.value
  if (!v || !loaded.value || applying) return
  applying = true
  try {
    if (appliedRepr !== reprKind.value) {
      reprBusy.value = true
      try {
        await applyMolstarStructurePreset(v, reprKind.value)
        appliedRepr = reprKind.value
      } finally {
        reprBusy.value = false
      }
    }
    if (colorMode.value === 'hydro-patch') {
      await applyMolstarHydroPatchTheme(v, {
        residueColors: residueColors.value,
        residuePatch: residuePatch.value,
        focusPatchId: props.selectedPatchId,
      })
      const items = props.selectedResidue
        ? [{ chain_id: props.selectedResidue.chainId, seq_num: props.selectedResidue.resi }]
        : patchResidueItems(selectedPatch.value ?? undefined, props.residues)
      highlightMolstarResidues(v, items, 'select')
      if (items.length) focusMolstarResidues(v, items)
    } else {
      await applyMolstarColorMode(v, colorMode.value === 'plddt' ? 'plddt' : 'chain')
    }
  } finally {
    applying = false
  }
}

async function mount(): Promise<void> {
  if (!props.cifText || !viewerEl.value) return
  loading.value = true
  loadError.value = ''
  appliedRepr = null
  pickUnsub?.unsubscribe()
  destroyMolstarViewer(viewer.value, viewerEl.value)
  try {
    for (let i = 0; i < 20; i += 1) {
      await nextTick()
      if (viewerEl.value && viewerEl.value.clientWidth > 8) break
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    }
    lastSize = { w: 0, h: 0 }
    const v = await createMolstarViewer(viewerEl.value, {
      illumination: false,
      layoutIsExpanded: false,
      viewportShowExpand: false,
      viewportBackgroundColor: '0xeef2f6',
    })
    viewer.value = v
    try {
      const layout = v.plugin.layout as { setProps?: (p: { isExpanded: boolean }) => void }
      layout.setProps?.({ isExpanded: false })
    } catch {
      /* 旧版 Mol* 无此 API */
    }
    await loadMolstarCif(v, props.cifText)
    pickUnsub = bindMolstarResiduePick(v, (chainId, resi) => {
      emit('residue-click', { chainId, resi })
    })
    loaded.value = true
    await applyTheme()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '3D 加载失败'
    loaded.value = false
  } finally {
    loading.value = false
    await nextTick()
    lastSize = { w: 0, h: 0 }
    fitViewer()
  }
}

watch(
  () => props.cifText,
  () => {
    loaded.value = false
    void mount()
  },
)

watch(
  [
    () => props.selectedPatchId,
    () => props.selectedResidue?.chainId,
    () => props.selectedResidue?.resi,
    () => props.patches.length,
    colorMode,
    reprKind,
  ],
  () => {
    void applyTheme()
  },
)

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined' && wrapEl.value) {
    resizeObserver = new ResizeObserver(() => scheduleFit())
    resizeObserver.observe(wrapEl.value)
  }
  void mount()
})

onBeforeUnmount(() => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeObserver?.disconnect()
  pickUnsub?.unsubscribe()
  destroyMolstarViewer(viewer.value, viewerEl.value)
  viewer.value = null
})
</script>

<template>
  <div class="hydro-viewer">
    <div ref="wrapEl" class="hydro-viewer__wrap" :class="{ loading }">
      <div ref="viewerEl" class="hydro-viewer__canvas molstar-viewer-host" />

      <div class="hydro-viewer__overlay">
        <div class="seg" role="group" aria-label="表示">
          <button
            type="button"
            :class="{ on: reprKind === 'molecular-surface' }"
            @click="reprKind = 'molecular-surface'"
          >
            分子表面
          </button>
          <button
            type="button"
            :class="{ on: reprKind === 'polymer-cartoon' }"
            @click="reprKind = 'polymer-cartoon'"
          >
            Cartoon
          </button>
        </div>
        <div class="seg" role="group" aria-label="着色">
          <button type="button" :class="{ on: colorMode === 'hydro-patch' }" @click="colorMode = 'hydro-patch'">
            {{ patchColorLabel }}
          </button>
          <button type="button" :class="{ on: colorMode === 'chain' }" @click="colorMode = 'chain'">按链</button>
          <button type="button" :class="{ on: colorMode === 'plddt' }" @click="colorMode = 'plddt'">pLDDT</button>
        </div>
      </div>

      <div v-if="colorMode === 'hydro-patch' && patches.length" class="hydro-viewer__legend">
        <span class="legend-chip">
          <i class="swatch" style="background: #e8edf3" />
          非斑
        </span>
        <button
          v-for="p in patches"
          :key="p.patch_id"
          type="button"
          class="legend-chip"
          :class="{ on: selectedPatchId === p.patch_id }"
          @click="emit('select-patch', selectedPatchId === p.patch_id ? null : p.patch_id)"
        >
          <i class="swatch" :style="{ background: p.color }" />
          {{ p.patch_id }}
        </button>
      </div>

      <div v-if="loading || loadError || !cifText" class="hydro-viewer__mask">
        {{ loadError || (loading ? '正在加载结构…' : '暂无 pred.cif') }}
      </div>
      <div v-else-if="reprBusy" class="hydro-viewer__busy">正在计算分子表面…</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.hydro-viewer {
  display: block;
  height: 640px;
  min-height: 560px;
}

.hydro-viewer__wrap {
  position: relative;
  height: 100%;
  min-height: 0;
  border-radius: 16px;
  overflow: hidden;
  isolation: isolate;
  border: 1px solid var(--border);
  background: #eef2f6;
}

.hydro-viewer__canvas {
  position: relative;
  width: 100%;
  height: 100%;
}

.hydro-viewer__overlay {
  position: absolute;
  top: 0.7rem;
  left: 0.7rem;
  z-index: 3;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  pointer-events: none;

  > * {
    pointer-events: auto;
  }
}

.seg {
  display: inline-flex;
  padding: 3px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(8px);

  button {
    border: none;
    background: transparent;
    padding: 0.32rem 0.7rem;
    border-radius: 8px;
    font-size: 0.75rem;
    color: var(--muted);
    cursor: pointer;

    &.on {
      background: #0f766e;
      color: #fff;
      font-weight: 600;
    }
  }
}

.hydro-viewer__legend {
  position: absolute;
  left: 0.7rem;
  right: 0.7rem;
  bottom: 0.7rem;
  z-index: 3;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  pointer-events: none;

  > * {
    pointer-events: auto;
  }
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.92);
  font-size: 0.72rem;
  color: #334155;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);

  &.on {
    border-color: #99f6e4;
    background: #ecfdf5;
    color: #0f766e;
    font-weight: 700;
  }
}

.swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid rgba(15, 23, 42, 0.12);
}

.hydro-viewer__mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(238, 242, 246, 0.82);
  font-size: 0.85rem;
  color: var(--muted);
  pointer-events: none;
}

.hydro-viewer__busy {
  position: absolute;
  top: 0.7rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 4;
  padding: 0.32rem 0.8rem;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.78);
  color: #fff;
  font-size: 0.75rem;
  pointer-events: none;
}
</style>
