<script setup lang="ts">
import { computed } from 'vue'
import type { CdrSpan, VersionChain, VersionMutation } from '@/api/antibodyProjects'

const props = defineProps<{
  chain: VersionChain
  parentChain?: VersionChain | null
  parentLabel: string
  childLabel: string
  mutations: VersionMutation[]
}>()

const childSpans = computed(() => parseCdrSpans(props.chain.annotation_json))
const parentSpans = computed(() => parseCdrSpans(props.parentChain?.annotation_json))
const childLabels = computed(() => parseKabatLabels(props.chain.annotation_json, props.chain.variable_sequence))
const parentLabels = computed(() =>
  parseKabatLabels(props.parentChain?.annotation_json, props.parentChain?.variable_sequence || ''),
)

const mutationIndex = computed(() => {
  const set = new Set<number>()
  for (const item of props.mutations) {
    if (item.chain_role === props.chain.chain_role && item.sequence_position) {
      set.add(item.sequence_position)
    }
  }
  return set
})

function parseCdrSpans(raw: VersionChain['annotation_json'] | undefined): CdrSpan[] {
  if (!raw || typeof raw !== 'object') return []
  const spans = (raw as { cdr_spans?: unknown }).cdr_spans
  if (!Array.isArray(spans)) return []
  return spans.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const row = item as Record<string, unknown>
    const name = String(row.name || '')
    const start = Number(row.start)
    const end = Number(row.end)
    if (!name || !Number.isFinite(start) || !Number.isFinite(end)) return []
    return [{
      name,
      start,
      end,
      kabat_range: row.kabat_range ? String(row.kabat_range) : undefined,
      sequence: row.sequence ? String(row.sequence) : undefined,
    }]
  })
}

function parseKabatLabels(raw: VersionChain['annotation_json'] | undefined, sequence: string): string[] {
  if (!raw || typeof raw !== 'object') {
    return sequence.split('').map((_, i) => String(i + 1))
  }
  const labels = (raw as { kabat_labels?: unknown }).kabat_labels
  if (!Array.isArray(labels)) return sequence.split('').map((_, i) => String(i + 1))
  return sequence.split('').map((_, i) => String(labels[i] ?? i + 1))
}

function cdrTone(spans: CdrSpan[], index0: number) {
  const span = spans.find((item) => index0 >= item.start && index0 <= item.end)
  if (!span) return ''
  const key = span.name.toUpperCase()
  if (key.includes('1')) return 'is-cdr1'
  if (key.includes('2')) return 'is-cdr2'
  if (key.includes('3')) return 'is-cdr3'
  return 'is-cdr'
}

function cdrStartName(spans: CdrSpan[], index0: number) {
  return spans.find((item) => item.start === index0)?.name || ''
}

function residues(sequence: string, spans: CdrSpan[], labels: string[], markMutations: boolean) {
  return sequence.split('').map((aa, index0) => ({
    aa,
    pos: index0 + 1,
    kabat: labels[index0] || String(index0 + 1),
    tone: cdrTone(spans, index0),
    cdrStart: cdrStartName(spans, index0),
    mutated: markMutations && mutationIndex.value.has(index0 + 1),
  }))
}

const parentResidues = computed(() => {
  const sequence = props.parentChain?.variable_sequence
  if (!sequence) return []
  return residues(sequence, parentSpans.value, parentLabels.value, true)
})

const childResidues = computed(() =>
  residues(props.chain.variable_sequence, childSpans.value, childLabels.value, true),
)

const displaySpans = computed(() => childSpans.value.length ? childSpans.value : parentSpans.value)
</script>

<template>
  <div class="seq-pair">
    <div class="seq-pair__head">
      <strong>{{ chain.chain_role }}</strong>
      <span>{{ chain.variable_sequence.length }} aa · Kabat</span>
      <span v-if="chain.nucleotide_sequence">核酸 {{ chain.nucleotide_sequence.length }} bp</span>
    </div>

    <div class="seq-legend">
      <span class="leg is-fw">框架区</span>
      <span class="leg is-cdr1">CDR1</span>
      <span class="leg is-cdr2">CDR2</span>
      <span class="leg is-cdr3">CDR3</span>
      <span class="leg is-mut">相对父本突变</span>
    </div>

    <div v-if="parentChain" class="seq-row">
      <div class="seq-row__label">父本 {{ parentLabel }}</div>
      <div class="seq-row__letters">
        <span
          v-for="item in parentResidues"
          :key="`p-${item.pos}`"
          class="aa"
          :class="[item.tone, { 'is-mut': item.mutated, 'is-cdr-start': !!item.cdrStart }]"
          :title="`序列 ${item.pos} · Kabat ${item.kabat}`"
        >
          <em v-if="item.cdrStart">{{ item.cdrStart }}</em>
          <span class="aa-num">{{ item.pos }}</span>
          <span class="aa-letter">{{ item.aa }}</span>
        </span>
      </div>
    </div>

    <div class="seq-row">
      <div class="seq-row__label">本版 {{ childLabel }}</div>
      <div class="seq-row__letters">
        <span
          v-for="item in childResidues"
          :key="`c-${item.pos}`"
          class="aa"
          :class="[item.tone, { 'is-mut': item.mutated, 'is-cdr-start': !!item.cdrStart }]"
          :title="`序列 ${item.pos} · Kabat ${item.kabat}`"
        >
          <em v-if="item.cdrStart">{{ item.cdrStart }}</em>
          <span class="aa-num">{{ item.pos }}</span>
          <span class="aa-letter">{{ item.aa }}</span>
        </span>
      </div>
    </div>

    <div v-if="displaySpans.length" class="cdr-chips">
      <span v-for="span in displaySpans" :key="span.name" class="cdr-chip" :class="cdrTone([span], span.start)">
        <b>{{ span.name }}</b>
        <small v-if="span.kabat_range">Kabat {{ span.kabat_range }}</small>
        <code>{{ span.sequence || chain.variable_sequence.slice(span.start, span.end + 1) }}</code>
      </span>
    </div>
    <p v-else class="seq-pair__hint">暂无 ANARCI 编号，无法标出 CDR。序列仍完整显示。</p>
  </div>
</template>

<style scoped lang="scss">
.seq-pair {
  min-width: 0;
  padding: 0.85rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
}

.seq-pair__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.45rem 0.75rem;
  margin-bottom: 0.45rem;
  font-size: 0.8rem;

  strong { color: var(--title); }
  span { color: var(--muted); }
}

.seq-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 0.7rem;
  margin-bottom: 0.7rem;
}

.leg {
  font-size: 0.7rem;
  color: var(--muted);

  &::before {
    content: '';
    display: inline-block;
    width: 10px;
    height: 10px;
    margin-right: 0.28rem;
    border-radius: 2px;
    vertical-align: -1px;
  }
  &.is-fw::before { background: #e5e7eb; }
  &.is-cdr1::before { background: #fb923c; }
  &.is-cdr2::before { background: #14b8a6; }
  &.is-cdr3::before { background: #3b82f6; }
  &.is-mut::before {
    background: #fff;
    box-shadow: inset 0 0 0 2px #dc2626;
  }
}

.seq-row + .seq-row { margin-top: 0.7rem; }

.seq-row__label {
  margin-bottom: 0.28rem;
  color: var(--muted);
  font-size: 0.74rem;
  font-weight: 700;
}

.seq-row__letters {
  display: flex;
  flex-wrap: wrap;
  row-gap: 1.55rem;
  padding: 0.95rem 0 0.15rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1;
}

.aa {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  width: 1.7em;
  min-height: 2.15em;
  padding: 0.12rem 0 0.08rem;
  text-align: center;
  color: #334155;
  border-radius: 3px;

  em {
    position: absolute;
    top: -0.85rem;
    left: 0;
    font-style: normal;
    font-size: 0.48rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    white-space: nowrap;
    color: inherit;
    z-index: 1;
  }

  .aa-num {
    font-size: 0.48rem;
    font-weight: 600;
    line-height: 1;
    color: #64748b;
    font-variant-numeric: tabular-nums;
  }

  .aa-letter {
    margin-top: 0.08rem;
    font-size: 0.8rem;
    font-weight: 700;
    line-height: 1;
  }

  &.is-cdr1 { background: #ffedd5; color: #9a3412; }
  &.is-cdr2 { background: #ccfbf1; color: #0f766e; }
  &.is-cdr3 { background: #dbeafe; color: #1d4ed8; }
  &.is-cdr1 .aa-num,
  &.is-cdr2 .aa-num,
  &.is-cdr3 .aa-num { color: inherit; opacity: 0.72; }
  &.is-mut {
    box-shadow: inset 0 -2px 0 #dc2626;
    .aa-letter { font-weight: 800; }
  }
}

.cdr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.85rem;
}

.cdr-chip {
  display: grid;
  gap: 0.12rem;
  min-width: 0;
  max-width: 100%;
  padding: 0.4rem 0.55rem;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid var(--border);
  font-size: 0.72rem;

  b { color: var(--title); }
  small { color: var(--muted); }
  code {
    overflow-wrap: anywhere;
    word-break: break-word;
    font-family: ui-monospace, Menlo, Consolas, monospace;
    color: #0f172a;
  }

  &.is-cdr1 { background: #fff7ed; border-color: #fdba74; }
  &.is-cdr2 { background: #f0fdfa; border-color: #5eead4; }
  &.is-cdr3 { background: #eff6ff; border-color: #93c5fd; }
}

.seq-pair__hint {
  margin: 0.7rem 0 0;
  color: var(--muted);
  font-size: 0.76rem;
}
</style>
