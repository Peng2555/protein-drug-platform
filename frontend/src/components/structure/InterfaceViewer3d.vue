<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
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
    const radius = IX_LINE_RADIUS[ix.type] ?? 0.04
    const start = { x: ix.coord_a[0], y: ix.coord_a[1], z: ix.coord_a[2] }
    const end = { x: ix.coord_b[0], y: ix.coord_b[1], z: ix.coord_b[2] }
    v.addCylinder({ start, end, radius, color, fromCap: 1, toCap: 1 })
    if (ix.type === 'hbond' || ix.type === 'salt_bridge') {
      v.addSphere({ center: start, radius: ix.type === 'salt_bridge' ? 0.18 : 0.12, color })
      v.addSphere({ center: end, radius: ix.type === 'salt_bridge' ? 0.18 : 0.12, color })
    }
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
      v.setStyle({ chain: ch.chain_id }, { cartoon: { opacity: 0 } })
      continue
    }
    const baseColor = palette[ch.chain_id] ?? hexColorToInt(ch.color)
    v.setStyle({ chain: ch.chain_id }, {
      cartoon: { color: baseColor, opacity: 0.2, thickness: 0.22 },
    })
  }

  for (const r of ifaceRes) {
    const key = `${r.chain_id}:${r.seq_num}`
    const baseColor = palette[r.chain_id] ?? IFACE_CHAIN_PALETTE.target
    const inIx = ixResKeys.has(key)
    v.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
      cartoon: {
        color: baseColor,
        opacity: inIx ? 1 : 0.82,
        thickness: inIx ? 0.52 : 0.4,
      },
    })
    if (inIx) {
      v.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
        stick: { colorscheme: 'greenCarbon', radius: 0.11, opacity: 0.88 },
      })
    }
  }

  drawInterfaceInteractionGraphics(v, interactions)

  const focusSelections: Array<{ chain: string; resi: number }> = []
  for (const key of ixResKeys.size ? ixResKeys : ifaceKeys) {
    const [chain, resi] = key.split(':')
    focusSelections.push({ chain, resi: parseInt(resi, 10) })
  }
  return focusSelections
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

const showHydrophobicNote = computed(() => {
  const primary = primaryInterface.value
  if (!primary) return false
  return (primary.interactions || []).some((ix) => ix.type === 'hydrophobic')
})

async function loadViewer(): Promise<void> {
  const primary = primaryInterface.value
  if (!primary?.contact_pairs || !props.cifText || !viewerEl.value) {
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = null
    return
  }

  try {
    await load3DmolLib()
    destroyViewer(viewer.value, viewerEl.value)
    viewer.value = createViewer(viewerEl.value, '0xf8fafc')
    viewer.value.addModel(props.cifText, 'cif')

    const focusSelections = paintInterfaceViewer(viewer.value, primary, chains.value)
    if (focusSelections.length) {
      viewer.value.zoomTo({ or: focusSelections })
      viewer.value.zoom(1.12)
    } else {
      viewer.value.zoomTo()
    }
    viewer.value.render()
  } catch (e) {
    console.error('interface viewer', e)
  }
}

function focusInteraction(ix: InterfaceInteraction | null | undefined): void {
  if (!viewer.value || !ix?.coord_a?.length || !ix.coord_b?.length) return
  const mid = {
    x: (ix.coord_a[0] + ix.coord_b[0]) / 2,
    y: (ix.coord_a[1] + ix.coord_b[1]) / 2,
    z: (ix.coord_a[2] + ix.coord_b[2]) / 2,
  }
  viewer.value.zoomTo({ center: mid, radius: 7 })
  viewer.value.render()
}

watch(
  () => [props.cifText, props.data, primaryInterface.value] as const,
  () => {
    void loadViewer()
  },
  { immediate: true, deep: true },
)

onBeforeUnmount(() => {
  destroyViewer(viewer.value, viewerEl.value)
  viewer.value = null
})

defineExpose({ focusInteraction, getViewer: () => viewer.value })
</script>

<template>
  <div v-if="primaryInterface?.contact_pairs" class="interface-viewer-shell">
    <div ref="viewerEl" class="interface-viewer__canvas" />

    <div class="interface-viewer-overlay">
      <div class="interface-viewer-overlay-title">结合界面</div>
      <div
        v-for="ch in overlayChainRows"
        :key="ch.id"
        class="interface-viewer-overlay-row"
      >
        <span class="interface-viewer-swatch" :style="{ background: hexCssFromInt(ch.color) }" />
        <span>{{ ch.label }} · 链 {{ ch.id }}</span>
      </div>

      <template v-if="overlayIxRows.length">
        <div class="interface-viewer-overlay-title overlay-ix-title">PLIP 相互作用</div>
        <div
          v-for="row in overlayIxRows"
          :key="row.type"
          class="interface-viewer-overlay-row"
        >
          <span class="interface-viewer-line" :style="{ background: row.css }" />
          <span>{{ row.label }}</span>
        </div>
      </template>

      <div v-if="showHydrophobicNote" class="interface-viewer-overlay-note">
        疏水接触见下方表格（3D 中省略以避免线网过密）
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.interface-viewer-shell {
  position: relative;
  border-radius: calc(var(--radius-sm) + 2px);
  overflow: hidden;
  height: min(620px, 62vh);
  min-height: 420px;
  border: 1px solid #dbe3ee;
  background: linear-gradient(165deg, #ffffff 0%, #f8fafc 48%, #eef2f7 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.interface-viewer__canvas {
  width: 100%;
  height: 100%;
}

.interface-viewer-overlay {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 20;
  max-width: min(320px, calc(100% - 28px));
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid rgba(203, 213, 225, 0.95);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  font-size: 0.72rem;
  color: var(--body);
  pointer-events: none;
}

.interface-viewer-overlay-title {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.35rem;

  &.overlay-ix-title {
    margin-top: 0.45rem;
  }
}

.interface-viewer-overlay-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0.2rem 0;
}

.interface-viewer-swatch {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  flex-shrink: 0;
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.interface-viewer-line {
  width: 24px;
  height: 3px;
  border-radius: 999px;
  flex-shrink: 0;
}

.interface-viewer-overlay-note {
  margin-top: 0.45rem;
  padding-top: 0.4rem;
  border-top: 1px dashed var(--border);
  font-size: 0.65rem;
  color: var(--muted);
  line-height: 1.35;
}
</style>
