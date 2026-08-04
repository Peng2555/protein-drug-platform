<script setup lang="ts">
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

function cdrClass(name?: string | null) {
  if (!name) return 'seg-fw'
  return `seg-${name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`
}

function cdrClassForResidue(ch: ChainSequence, index: number) {
  const i = index - 1
  for (const sp of ch.cdr_spans || []) {
    if (i >= sp.start && i <= sp.end) return cdrClass(sp.name)
  }
  return 'seg-fw'
}

function residuesForChain(ch: ChainSequence) {
  if (ch.residues?.length) return ch.residues
  return (ch.sequence || '').split('').map((aa, i) => ({
    index: i + 1,
    aa,
    kabat: String(i + 1),
  }))
}

function onResidueClick(chainId: string, resi: number, event: MouseEvent) {
  selectionStore.selectSequenceResidue(chainId, resi, event)
}

function clearSelection() {
  selectionStore.clearSequenceResidueSelection()
}
</script>

<template>
  <section v-if="chains.length" class="sequence-panel page-card">
    <div class="sequence-panel__head">
      <h3>序列 · Kabat 编号</h3>
      <div class="sequence-panel__actions">
        <span v-if="selectionCount" class="seq-selection-count">已选 {{ selectionCount }} 个残基</span>
        <el-button v-if="selectionCount" size="small" plain @click="clearSelection">清除选中</el-button>
      </div>
    </div>

    <div class="sequence-legend">
      <span class="legend-fw">框架区</span>
      <span class="legend-cdr1">CDR1 (H1/L1)</span>
      <span class="legend-cdr2">CDR2 (H2/L2)</span>
      <span class="legend-cdr3">CDR3 (H3/L3)</span>
      <span class="legend-pymol-sel">PyMOL 选中</span>
      <span class="legend-hint">点击添加/取消 · Shift 连选同链区间 · Ctrl 同点击</span>
    </div>

    <div
      v-for="ch in chains"
      :key="ch.chain_id"
      class="chain-seq-block"
    >
      <div class="chain-seq-head">
        <strong>&gt;{{ ch.chain_id }}</strong>
        <span>
          {{
            ch.is_antibody
              ? `${ch.domain} 链 · Kabat · ${ch.length} aa`
              : `非抗体链 · 序列位 1–${ch.length}`
          }}
        </span>
      </div>

      <div class="chain-seq-body">
        <div
          class="chain-seq-numbered"
          :style="{ '--seq-len': residuesForChain(ch).length }"
        >
          <div class="seq-res-grid">
          <span
            v-for="r in residuesForChain(ch)"
            :key="`${ch.chain_id}-${r.index}`"
            class="res-cell res-selectable"
            :class="[
              cdrClassForResidue(ch, r.index),
              { 'res-selected': selectionStore.isResidueSelected(ch.chain_id, r.index) },
            ]"
            :title="
              ch.is_antibody && r.kabat && String(r.kabat) !== String(r.index)
                ? `序列位 ${r.index} · Kabat ${r.kabat} · 点击多选`
                : `序列位 ${r.index} · 点击多选`
            "
            @click="onResidueClick(ch.chain_id, r.index, $event)"
          >
            <span class="res-num">
              {{ ch.is_antibody && r.kabat && String(r.kabat) !== String(r.index) ? r.kabat : r.index }}
            </span>
            <span class="res-aa">{{ r.aa }}</span>
          </span>
        </div>
      </div>
      </div>

      <div v-if="ch.cdr_spans?.length" class="cdr-tags">
        <span v-for="sp in ch.cdr_spans" :key="sp.name" class="cdr-tag">
          {{ sp.name }} ({{ sp.kabat_range }}):
          <code>{{ sp.sequence }}</code>
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/sequence.scss';
</style>
