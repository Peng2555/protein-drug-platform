<script setup lang="ts">
export type SubmissionMode = 'single' | 'batch'

defineProps<{ modelValue: SubmissionMode }>()
const emit = defineEmits<{ 'update:modelValue': [value: SubmissionMode] }>()
</script>

<template>
  <div class="mode-tabs" role="tablist">
    <button
      type="button"
      :class="{ active: modelValue === 'single' }"
      @click="emit('update:modelValue', 'single')"
    >
      单条
    </button>
    <button
      type="button"
      :class="{ active: modelValue === 'batch' }"
      @click="emit('update:modelValue', 'batch')"
    >
      批量
    </button>
  </div>
</template>

<style scoped lang="scss">
.mode-tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 1.1rem;
  padding: 0.25rem;
  width: fit-content;
  border-radius: 10px;
  background: #f3f4f6;

  button {
    border: none;
    background: transparent;
    padding: 0.35rem 0.9rem;
    border-radius: 8px;
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--muted);
    cursor: pointer;

    &.active {
      background: #fff;
      color: var(--title);
    }
  }
}
</style>
