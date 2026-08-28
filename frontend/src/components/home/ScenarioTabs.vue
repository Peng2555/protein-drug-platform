<script setup lang="ts">
import type { ScenarioDef, ScenarioId } from '@/config/workflows'

defineProps<{
  scenarios: ScenarioDef[]
  modelValue: ScenarioId
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ScenarioId]
}>()
</script>

<template>
  <div class="scenario-tabs" role="tablist">
    <button
      v-for="s in scenarios"
      :key="s.id"
      type="button"
      role="tab"
      class="scenario-tabs__btn"
      :class="{ 'scenario-tabs__btn--active': modelValue === s.id }"
      :aria-selected="modelValue === s.id"
      @click="emit('update:modelValue', s.id)"
    >
      {{ s.label }}
    </button>
  </div>
</template>

<style scoped lang="scss">
.scenario-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.scenario-tabs__btn {
  padding: 0.48rem 1rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--body);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.35);
    color: var(--bio-green-dark);
  }

  &--active {
    border-color: transparent;
    color: #fff;
    background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
    box-shadow: 0 4px 14px rgba(0, 122, 114, 0.22);
  }
}
</style>
