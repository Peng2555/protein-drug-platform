<script setup lang="ts">
import type { BatchDetail } from '@/api/types'
import { batchStatusLabel } from '@/utils/constants'

defineProps<{
  batch: BatchDetail
  kicker: string
}>()
</script>

<template>
  <div class="batch-detail-page">
    <header class="batch-detail-top">
      <div>
        <p class="kicker">{{ kicker }}</p>
        <h1>{{ batch.name }}</h1>
        <p class="meta">
          {{ new Date(batch.created_at).toLocaleString('zh-CN') }}
          · {{ batch.done_count }}/{{ batch.heavy_chain_count }} 完成
          · 运行 {{ batch.running_count }} · 排队 {{ batch.queued_count }} · 失败
          {{ batch.failed_count }}
        </p>
      </div>
      <div class="actions">
        <span class="status-pill" :data-status="batch.status">
          {{ batchStatusLabel(batch.status) }}
        </span>
        <slot name="actions" />
      </div>
    </header>
    <slot />
    <p class="hint"><slot name="hint" /></p>
  </div>
</template>

<style scoped lang="scss">
.batch-detail-page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2.5rem;
}
.batch-detail-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  h1 {
    margin: 0.15rem 0 0;
    font-size: 1.45rem;
  }
}
.kicker {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.meta {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
}
.status-pill {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: #f3f4f6;
  &[data-status='done'] {
    background: #ecfdf5;
    color: #047857;
  }
  &[data-status='running'],
  &[data-status='queued'],
  &[data-status='partial'] {
    background: #fff7ed;
    color: #c2410c;
  }
  &[data-status='failed'] {
    background: #fef2f2;
    color: #b91c1c;
  }
}
.hint {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
