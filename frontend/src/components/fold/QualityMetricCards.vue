<script setup lang="ts">
import { levelLabel, type FoldScoreCard } from '@/types/foldWorkbench'

defineProps<{
  cards: FoldScoreCard[]
}>()
</script>

<template>
  <div class="quality-cards">
    <div
      v-for="card in cards"
      :key="card.key"
      class="quality-card"
      :class="[
        `quality-card--${card.tone}`,
        card.level ? `is-${card.level}` : '',
      ]"
    >
      <div class="quality-card__top">
        <span class="quality-card__label">{{ card.label }}</span>
        <span v-if="card.level" class="quality-card__level">{{ levelLabel(card.level) }}</span>
      </div>
      <div class="quality-card__value">{{ card.value }}</div>
      <div class="quality-card__hint">{{ card.hint }}</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.quality-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.55rem;
}

.quality-card {
  padding: 0.75rem 0.8rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--card);
  box-shadow: var(--shadow);

  &__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.35rem;
  }

  &__label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
  }

  &__level {
    font-size: 0.66rem;
    font-weight: 700;
    padding: 0.08rem 0.4rem;
    border-radius: 999px;
    background: var(--bg-soft);
    color: var(--body);
  }

  &__value {
    margin-top: 0.2rem;
    font-size: 1.28rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    font-family: var(--mono);
    color: var(--title);
    line-height: 1.15;
  }

  &__hint {
    margin-top: 0.25rem;
    font-size: 0.68rem;
    color: var(--muted);
    line-height: 1.35;
  }

  &--primary .quality-card__value { color: var(--bio-blue); }
  &--ok .quality-card__value { color: var(--bio-green-dark); }
  &--warn .quality-card__value { color: #b45309; }
  &--info .quality-card__value { color: #475569; }

  &.is-high .quality-card__level {
    background: var(--bio-green-light);
    color: var(--bio-green-dark);
  }
  &.is-mid .quality-card__level {
    background: #fff7ed;
    color: #c2410c;
  }
  &.is-low .quality-card__level {
    background: #fef2f2;
    color: #b91c1c;
  }
}
</style>
