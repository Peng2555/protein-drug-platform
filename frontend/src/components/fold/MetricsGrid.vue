<script setup lang="ts">
import { computed } from 'vue'

export interface MetricItem {
  label: string
  value: string | number | null | undefined
  highlight?: boolean
}

const props = defineProps<{
  items: MetricItem[]
}>()

const normalized = computed(() =>
  props.items.map((m) => ({
    ...m,
    display:
      m.value != null
        ? typeof m.value === 'number'
          ? m.value.toFixed(3)
          : String(m.value)
        : '—',
  })),
)
</script>

<template>
  <div class="metrics-grid">
    <div
      v-for="(m, i) in normalized"
      :key="i"
      class="metric"
      :class="{ 'metric-highlight': m.highlight }"
    >
      <div class="val">{{ m.display }}</div>
      <div class="lbl">{{ m.label }}</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 0.65rem;
}

.metric {
  padding: 0.65rem 0.75rem;
  border-radius: var(--radius-sm);
  background: var(--bg-soft, #f8fafc);
  border: 1px solid var(--border);
  text-align: center;
}

.metric-highlight {
  background: var(--bio-green-light, #e6f7f5);
  border-color: rgba(0, 172, 161, 0.25);
}

.metric-highlight .val {
  color: var(--bio-green-dark);
}

.val {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--title);
  font-variant-numeric: tabular-nums;
}

.lbl {
  margin-top: 0.2rem;
  font-size: 0.72rem;
  color: var(--muted);
}
</style>
