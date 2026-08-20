<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
  tips?: string[]
}>()
</script>

<template>
  <section class="module-home page-card page-card--accent">
    <p class="module-home__kicker">当前模块</p>
    <h2>{{ title }}</h2>
    <p class="module-home__sub">{{ subtitle }}</p>
    <ul v-if="tips?.length" class="module-home__tips">
      <li v-for="tip in tips" :key="tip">{{ tip }}</li>
    </ul>
    <p class="module-home__guide">在左侧面板提交任务，或从任务列表打开已有结果。</p>
  </section>
</template>

<style scoped lang="scss">
.module-home {
  min-height: 420px;
  padding: 2.4rem 2.2rem;
}

.module-home__kicker {
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--bio-green-dark);
}

h2 {
  margin: 0 0 0.55rem;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--title);
}

.module-home__sub {
  margin: 0;
  max-width: 52rem;
  font-size: 0.92rem;
  line-height: 1.65;
  color: var(--body);
}

.module-home__tips {
  list-style: none;
  margin: 1.4rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.55rem;
  max-width: 44rem;
}

.module-home__tips li {
  position: relative;
  padding: 0.7rem 0.9rem 0.7rem 1.35rem;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  font-size: 0.84rem;
  color: var(--body);
  line-height: 1.5;
}

.module-home__tips li::before {
  content: '';
  position: absolute;
  left: 0.65rem;
  top: 1.05rem;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bio-green);
}

.module-home__guide {
  margin: 1.4rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
</style>
