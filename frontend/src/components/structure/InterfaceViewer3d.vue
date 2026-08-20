<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  cartoonStyle,
  createViewer,
  destroyViewer,
  hexColorToInt,
  load3DmolLib,
} from '@/composables/use3Dmol'
import type {
  InterfaceChainMeta,
  InterfaceInteraction,
  InterfacePair,
  JobInterfaceData,
  Mol3DViewer,
} from '@/types/structure'
import {
  IFACE_CHAIN_PALETTE,
  IX_COLORS,
  IX_DRAW_IN_3D,
  IX_LINE_CSS,
  IX_LINE_RADIUS,
  IX_TYPE_LABELS,
} from '@/types/structure'

export type { InterfaceInteraction } from '@/types/structure'

const props = defineProps<{
  cifText: string
  data: JobInterfaceData
  primary?: InterfacePair | null
}>()

const viewerEl = ref<HTMLElement | null>(null)
const viewer = ref<Mol3DViewer | null>(null)
const loadError = ref('')
const focusSelectionsCache = ref<Array<{ chain: string; resi: number }>>([])
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

function drawInterfaceInteractionGraphics(v: Mol3DViewer, interactions: InterfaceInteraction[]): void {
  for (const ix of interactions) {
    if (!IX_DRAW_IN_3D.has(ix.type)) continue
    if (!ix.coord_a?.length || !ix.coord_b?.length) continue
    const color = IX_COLORS[ix.type] ?? 0x64748b
    const radius = IX_LINE_RADIUS[ix.type] ?? 0.02
    const start = { x: ix.coord_a[0], y: ix.coord_a[1], z: ix.coord_a[2] }
    const end = { x: ix.coord_b[0], y: ix.coord_b[1], z: ix.coord_b[2] }
    // Single thin cylinder between PLIP atom coordinates (non-covalent; not stick/bond inference).
    v.addCylinder({ start, end, radius, color, fromCap: 0, toCap: 0 })
  }
}

function paintInterfaceViewer(
  v: Mol3DViewer,
  primary: InterfacePair,
  chainList: InterfaceChainMeta[],
): Array<{ chain: string; resi: number }> {
  const palette = getInterfaceChainPalette(primary, chainList)
  const { interactions, ixResKeys } = collectInterfaceResidueKeys(primary)
  const ifaceRes = [...(primary.residues_a || []), ...(primary.residues_b || [])]
  const ifaceKeys = new Set(ifaceRes.map((r) => `${r.chain_id}:${r.seq_num}`))

  for (const ch of chainList) {
    const onIface = ch.chain_id === primary.chain_a || ch.chain_id === primary.chain_b
    if (!onIface) {
      v.setStyle({ chain: ch.chain_id }, { cartoon: cartoonStyle({ opacity: 0 }) })
      continue
    }
    const baseColor = palette[ch.chain_id] ?? hexColorToInt(ch.color)
    v.setStyle({ chain: ch.chain_id }, {
      cartoon: cartoonStyle({ color: baseColor, opacity: 0.22, thickness: 0.28, width: 0.9 }),
    })
  }

  // Cartoon only — no stick (avoids 3Dmol distance-based false bonds at crowded interfaces).
  for (const r of ifaceRes) {
    const key = `${r.chain_id}:${r.seq_num}`
    const baseColor = palette[r.chain_id] ?? IFACE_CHAIN_PALETTE.target
    const inIx = ixResKeys.has(key)
    v.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
      cartoon: cartoonStyle({
        color: baseColor,
        opacity: inIx ? 0.98 : 0.78,
        thickness: inIx ? 0.5 : 0.38,
        width: inIx ? 1.45 : 1.15,
      }),
    })
  }

  drawInterfaceInteractionGraphics(v, interactions)

  const focusSelections: Array<{ chain: string; resi: number }> = []
  for (const key of ixResKeys.size ? ixResKeys : ifaceKeys) {
    const [chain, resi] = key.split(':')
    focusSelections.push({ chain, resi: parseInt(resi, 10) })
  }
  return focusSelections
}

function applyCamera(focusSelections: Array<{ chain: string; resi: number }>): void {
  if (!viewer.value) return
  if (focusSelections.length) {
    viewer.value.zoomTo({ or: focusSelections })
    viewer.value.zoom(1.15)
  } else {
    viewer.value.zoomTo()
  }
  viewer.value.render()
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

async function loadViewer(): Promise<void> {
  const primary = primaryInterface.value
  if (!primary?.contact_pairs || !props.cifText || !viewerEl.value) {
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = null
    return
  }

  loadError.value = ''
  try {
    await load3DmolLib()
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = createViewer(viewerEl.value, '0xf8fafc')
    viewer.value.addModel(props.cifText, 'cif')

    focusSelectionsCache.value = paintInterfaceViewer(viewer.value, primary, chains.value)
    applyCamera(focusSelectionsCache.value)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '3D 界面视图加载失败'
    console.error('interface viewer', e)
  }
}

function onViewerResize(): void {
  if (!viewerEl.value) return
  if (viewer.value) {
    viewer.value.render()
    return
  }
  if (viewerEl.value.clientWidth > 0 && viewerEl.value.clientHeight > 0) {
    scheduleLoadViewer()
  }
}

function scheduleLoadViewer(): void {
  void nextTick(() => loadViewer())
}

function resetView(): void {
  applyCamera(focusSelectionsCache.value)
}

function focusInteraction(ix: InterfaceInteraction | null | undefined): void {
  if (!viewer.value || !ix?.coord_a?.length || !ix.coord_b?.length) return
  const mid = {
    x: (ix.coord_a[0] + ix.coord_b[0]) / 2,
    y: (ix.coord_a[1] + ix.coord_b[1]) / 2,
    z: (ix.coord_a[2] + ix.coord_b[2]) / 2,
  }
  viewer.value.zoomTo({ center: mid, radius: 6.5 })
  viewer.value.render()
}

watch(
  () => [props.cifText, props.data, primaryInterface.value] as const,
  () => {
    scheduleLoadViewer()
  },
  { deep: true },
)

onMounted(() => {
  scheduleLoadViewer()
  const shell = viewerEl.value?.parentElement
  if (typeof ResizeObserver !== 'undefined' && shell) {
    resizeObserver = new ResizeObserver(() => onViewerResize())
    resizeObserver.observe(shell)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  destroyViewer(viewer.value, viewerEl.value)
  viewer.value = null
})

defineExpose({ focusInteraction, resetView, getViewer: () => viewer.value })
</script>

<template>
  <div v-if="primaryInterface?.contact_pairs" class="interface-viewer-shell">
    <div ref="viewerEl" class="interface-viewer__canvas" />

    <div class="interface-viewer-toolbar">
      <el-button size="small" round @click="resetView">重置视角</el-button>
    </div>

    <div v-if="loadError" class="interface-viewer-error">
      {{ loadError }}
    </div>

    <div class="interface-viewer-legend">
      <div class="interface-viewer-legend-title">链与界面</div>
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
        细线为 PLIP 原子坐标连线（氢键/盐桥，非共价键）
        <template v-if="showExtraIxNote">；π/疏水/水桥等见右侧表格</template>
      </div>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/interface.scss';
</style>
