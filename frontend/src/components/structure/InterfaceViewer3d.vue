<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  createMolstarViewer,
  destroyMolstarViewer,
  focusMolstarPoint,
  focusMolstarResidues,
  highlightMolstarResidues,
  loadMolstarCif,
  resizeMolstarViewer,
  type MolstarViewer,
} from '@/composables/useMolstar'
import type {
  InterfaceChainMeta,
  InterfaceInteraction,
  InterfacePair,
  JobInterfaceData,
} from '@/types/structure'
import {
  IFACE_CHAIN_PALETTE,
  IX_DRAW_IN_3D,
  IX_LINE_CSS,
  IX_TYPE_LABELS,
} from '@/types/structure'

export type { InterfaceInteraction } from '@/types/structure'

const props = defineProps<{
  cifText: string
  data: JobInterfaceData
  primary?: InterfacePair | null
}>()

const viewerEl = ref<HTMLElement | null>(null)
const viewer = shallowRef<MolstarViewer | null>(null)
const loadError = ref('')
const focusSelectionsCache = ref<Array<{ chain_id: string; seq_num: number }>>([])
let resizeObserver: ResizeObserver | null = null

const primaryInterface = computed(() => props.primary ?? props.data.primary_interface ?? null)
const chains = computed(() => props.data.chains ?? [])

function hexCssFromInt(colorInt: number): string {
  return `#${colorInt.toString(16).padStart(6, '0')}`
}

function getInterfaceChainPalette(primary: InterfacePair, chainList: InterfaceChainMeta[]) {
  const meta = Object.fromEntries(chainList.map((c) => [c.chain_id, c]))
  const palette: Record<string, number> = {}
  for (const cid of [primary.chain_a, primary.chain_b]) {
    const m = meta[cid] || {}
    const isTarget =
      m.role === 'target' ||
      (m.label && /靶|抗原|target/i.test(m.label)) ||
      cid === 'A'
    palette[cid] = isTarget ? IFACE_CHAIN_PALETTE.target : IFACE_CHAIN_PALETTE.binder
  }
  return palette
}

function collectInterfaceResidueKeys(primary: InterfacePair) {
  const interactions = (primary.interactions || []).filter((ix) => ix.type !== 'contact')
  const ixResKeys = new Set<string>()
  for (const ix of interactions) {
    ixResKeys.add(`${ix.chain_a}:${ix.resnum_a}`)
    ixResKeys.add(`${ix.chain_b}:${ix.resnum_b}`)
  }
  return { interactions, ixResKeys }
}

function buildFocusResidues(primary: InterfacePair, ixResKeys: Set<string>) {
  const ifaceRes = [...(primary.residues_a || []), ...(primary.residues_b || [])]
  const ifaceKeys = new Set(ifaceRes.map((r) => `${r.chain_id}:${r.seq_num}`))
  const keys = ixResKeys.size ? ixResKeys : ifaceKeys
  return [...keys].map((key) => {
    const [chain_id, seq_num] = key.split(':')
    return { chain_id, seq_num: parseInt(seq_num, 10) }
  })
}

async function loadViewer(): Promise<void> {
  const primary = primaryInterface.value
  if (!primary?.contact_pairs || !props.cifText || !viewerEl.value) {
    destroyMolstarViewer(viewer.value, viewerEl.value)
    viewer.value = null
    return
  }

  loadError.value = ''
  try {
    destroyMolstarViewer(viewer.value, viewerEl.value)
    const v = await createMolstarViewer(viewerEl.value, { viewportBackgroundColor: '0xf8fafc' })
    viewer.value = v
    await loadMolstarCif(v, props.cifText)

    const { ixResKeys } = collectInterfaceResidueKeys(primary)
    const ifaceRes = [...(primary.residues_a || []), ...(primary.residues_b || [])]
    const interactionResidues = [...ixResKeys].map((key) => {
      const [chain_id, seq_num] = key.split(':')
      return { chain_id, seq_num: parseInt(seq_num, 10) }
    })

    highlightMolstarResidues(v, ifaceRes, 'highlight')
    if (interactionResidues.length) {
      highlightMolstarResidues(v, interactionResidues, 'select')
    }

    focusSelectionsCache.value = buildFocusResidues(primary, ixResKeys)
    focusMolstarResidues(v, focusSelectionsCache.value)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '3D 界面视图加载失败'
    console.error('interface viewer', e)
  }
}

function onViewerResize(): void {
  resizeMolstarViewer(viewer.value)
  if (!viewer.value && viewerEl.value && viewerEl.value.clientWidth > 0) {
    void nextTick(() => loadViewer())
  }
}

const overlayChainRows = computed(() => {
  const primary = primaryInterface.value
  if (!primary) return []
  const palette = getInterfaceChainPalette(primary, chains.value)
  return [
    {
      id: primary.chain_a,
      label: primary.label_a || primary.chain_a,
      color: palette[primary.chain_a],
    },
    {
      id: primary.chain_b,
      label: primary.label_b || primary.chain_b,
      color: palette[primary.chain_b],
    },
  ]
})

const overlayIxRows = computed(() => {
  const primary = primaryInterface.value
  if (!primary) return []
  const presentIx = new Set((primary.interactions || []).map((ix) => ix.type))
  return Object.entries(IX_TYPE_LABELS)
    .filter(([k]) => presentIx.has(k) && IX_DRAW_IN_3D.has(k))
    .map(([k, lbl]) => ({ type: k, label: lbl, css: IX_LINE_CSS[k] }))
})

const showExtraIxNote = computed(() => {
  const primary = primaryInterface.value
  if (!primary) return false
  const types = new Set((primary.interactions || []).map((ix) => ix.type))
  return types.has('hydrophobic') || types.has('pi_stacking') || types.has('pi_cation') || types.has('water_bridge')
})

function resetView(): void {
  if (viewer.value) focusMolstarResidues(viewer.value, focusSelectionsCache.value)
}

function focusInteraction(ix: InterfaceInteraction | null | undefined): void {
  if (!viewer.value || !ix?.coord_a?.length || !ix.coord_b?.length) return
  focusMolstarPoint(viewer.value, {
    x: (ix.coord_a[0] + ix.coord_b[0]) / 2,
    y: (ix.coord_a[1] + ix.coord_b[1]) / 2,
    z: (ix.coord_a[2] + ix.coord_b[2]) / 2,
  })
  highlightMolstarResidues(viewer.value, [
    { chain_id: ix.chain_a, seq_num: ix.resnum_a },
    { chain_id: ix.chain_b, seq_num: ix.resnum_b },
  ], 'select')
}

watch(
  () => [props.cifText, props.data, primaryInterface.value] as const,
  () => { void loadViewer() },
  { deep: true },
)

onMounted(() => {
  void loadViewer()
  const shell = viewerEl.value?.parentElement
  if (typeof ResizeObserver !== 'undefined' && shell) {
    resizeObserver = new ResizeObserver(() => onViewerResize())
    resizeObserver.observe(shell)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  destroyMolstarViewer(viewer.value, viewerEl.value)
  viewer.value = null
})

defineExpose({ focusInteraction, resetView, getViewer: () => viewer.value })
</script>

<template>
  <div v-if="primaryInterface?.contact_pairs" class="interface-viewer-shell">
    <div ref="viewerEl" class="interface-viewer__canvas molstar-viewer-host" />

    <div class="interface-viewer-toolbar">
      <el-button size="small" round @click="resetView">重置视角</el-button>
    </div>

    <div v-if="loadError" class="interface-viewer-error">
      {{ loadError }}
    </div>

    <div class="interface-viewer-legend">
      <div class="interface-viewer-legend-title">链与界面 · Mol*</div>
      <div
        v-for="ch in overlayChainRows"
        :key="ch.id"
        class="interface-viewer-legend-row"
      >
        <span class="interface-viewer-swatch" :style="{ background: hexCssFromInt(ch.color) }" />
        <span>{{ ch.label }} · {{ ch.id }}</span>
      </div>

      <template v-if="overlayIxRows.length">
        <div class="interface-viewer-legend-title" style="margin-top: 0.45rem">相互作用</div>
        <div
          v-for="row in overlayIxRows"
          :key="row.type"
          class="interface-viewer-legend-row"
        >
          <span class="interface-viewer-line" :style="{ background: row.css }" />
          <span>{{ row.label }}</span>
        </div>
      </template>

      <div class="interface-viewer-legend-note">
        界面残基高亮由 Mol* 渲染；PLIP 详细相互作用见右侧表格
        <template v-if="showExtraIxNote">（π/疏水/水桥等）</template>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/interface.scss';

.molstar-viewer-host .msp-plugin {
  width: 100%;
  height: 100%;
}
</style>
