<script setup lang="ts">
/**
 * PyMOL 风格序列条：嵌在结构框底部，紧凑横向展示，与 3D 选中联动。
 */
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { ChainSequence } from '@/api/types'
import { useSelectionStore } from '@/composables/useSelection'

const props = defineProps<{
  chains: ChainSequence[]
}>()

const selectionStore = useSelectionStore()
const { selectedSeqResidues } = storeToRefs(selectionStore)

const selectionCount = computed(() => selectedSeqResidues.value.size)

function residuesForChain(ch: ChainSequence) {
  if (ch.residues?.length) return ch.residues
  return (ch.sequence || '').split('').map((aa, i) => ({
    index: i + 1,
    aa,
    kabat: String(i + 1),
  }))
}

function cdrClass(ch: ChainSequence, index: number) {
  const i = index - 1
  for (const sp of ch.cdr_spans || []) {
    if (i >= sp.start && i <= sp.end) {
      const key = (sp.name || '').toLowerCase()
      if (key.includes('1') || key.includes('h1') || key.includes('l1')) return 'is-cdr1'
      if (key.includes('2') || key.includes('h2') || key.includes('l2')) return 'is-cdr2'
      if (key.includes('3') || key.includes('h3') || key.includes('l3')) return 'is-cdr3'
    }
  }
  return ''
}

function onResidueClick(chainId: string, resi: number, event: MouseEvent) {
  selectionStore.selectSequenceResidue(chainId, resi, event)
}

function clearSelection() {
  selectionStore.clearSequenceResidueSelection()
}

function showNum(index: number) {
  return index === 1 || index % 10 === 0
}
</script>

<template>
  <div v-if="chains.length" class="seq-strip">
    <div class="seq-strip__bar">
      <div class="seq-strip__meta">
        <strong>Sequence</strong>
        <span class="leg is-fw">FW</span>
        <span class="leg is-cdr1">CDR1</span>
        <span class="leg is-cdr2">CDR2</span>
        <span class="leg is-cdr3">CDR3</span>
        <span v-if="selectionCount" class="sel-count">已选 {{ selectionCount }}</span>
        <button v-if="selectionCount" type="button" class="clear-btn" @click="clearSelection">清除</button>
      </div>
      <span class="seq-strip__hint">点击选残基 · Shift 连选 · Ctrl 多选</span>
    </div>

    <div class="seq-strip__chains">
      <div v-for="ch in chains" :key="ch.chain_id" class="seq-row">
        <div class="seq-row__id" :title="ch.is_antibody ? `${ch.domain} 链` : '非抗体链'">
          {{ ch.chain_id }}
        </div>
        <div class="seq-row__scroll">
          <div class="seq-row__aas">
            <button
              v-for="r in residuesForChain(ch)"
              :key="`${ch.chain_id}-${r.index}`"
              type="button"
              class="aa"
              :class="[
                cdrClass(ch, r.index),
                { 'is-selected': selectionStore.isResidueSelected(ch.chain_id, r.index) },
              ]"
              :title="`${ch.chain_id}${r.index} ${r.aa}`"
              @click="onResidueClick(ch.chain_id, r.index, $event)"
            >
              <span v-if="showNum(r.index)" class="aa-num">{{ r.index }}</span>
              <span class="aa-letter">{{ r.aa }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.seq-strip {
  flex-shrink: 0;
  border-top: 1px solid #1e293b;
  background: #0f172a;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.seq-strip__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.28rem 0.55rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  font-size: 0.68rem;
}

.seq-strip__meta {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  flex-wrap: wrap;

  strong {
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    color: #f8fafc;
  }
}

.leg {
  padding: 0.05rem 0.28rem;
  border-radius: 3px;
  font-size: 0.62rem;
  font-weight: 700;

  &.is-fw { background: #334155; color: #cbd5e1; }
  &.is-cdr1 { background: #c2410c; color: #fff7ed; }
  &.is-cdr2 { background: #0f766e; color: #ecfeff; }
  &.is-cdr3 { background: #1d4ed8; color: #eff6ff; }
}

.sel-count {
  color: #f472b6;
  font-weight: 700;
}

.clear-btn {
  border: 1px solid rgba(244, 114, 182, 0.45);
  background: transparent;
  color: #f9a8d4;
  border-radius: 4px;
  padding: 0.05rem 0.35rem;
  font-size: 0.62rem;
  cursor: pointer;
}

.seq-strip__hint {
  color: #94a3b8;
  white-space: nowrap;
}

.seq-strip__chains {
  max-height: 118px;
  overflow-y: auto;
  padding: 0.2rem 0 0.3rem;
}

.seq-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 0.2rem;
  align-items: center;
  min-height: 28px;
  padding: 0.08rem 0.35rem;
}

.seq-row__id {
  font-size: 0.72rem;
  font-weight: 800;
  color: #38bdf8;
  text-align: center;
}

.seq-row__scroll {
  overflow-x: auto;
  overflow-y: hidden;
}

.seq-row__aas {
  display: inline-flex;
  align-items: flex-end;
  min-width: max-content;
  padding-bottom: 1px;
}

.aa {
  position: relative;
  width: 12px;
  height: 22px;
  padding: 0;
  margin: 0;
  border: none;
  background: transparent;
  color: #e2e8f0;
  cursor: pointer;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  line-height: 1;

  &:hover {
    background: rgba(56, 189, 248, 0.22);
  }

  &.is-cdr1 .aa-letter { color: #fdba74; font-weight: 700; }
  &.is-cdr2 .aa-letter { color: #5eead4; font-weight: 700; }
  &.is-cdr3 .aa-letter { color: #93c5fd; font-weight: 700; }

  &.is-selected {
    background: #db2777;
    border-radius: 2px;

    .aa-letter,
    .aa-num {
      color: #fff !important;
    }
  }
}

.aa-num {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.48rem;
  color: #64748b;
  pointer-events: none;
  white-space: nowrap;
}

.aa-letter {
  font-size: 0.72rem;
  font-weight: 600;
}
</style>
