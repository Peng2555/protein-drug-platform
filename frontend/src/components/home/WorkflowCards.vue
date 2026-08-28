<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import type { WorkflowDef } from '@/config/workflows'

defineProps<{
  workflows: WorkflowDef[]
}>()

const router = useRouter()

function start(route: string) {
  router.push(route)
}
</script>

<template>
  <div class="workflow-grid">
    <article
      v-for="wf in workflows"
      :key="wf.id"
      class="workflow-card"
      :class="`workflow-card--${wf.accent}`"
    >
      <h3>{{ wf.title }}</h3>
      <p>{{ wf.description }}</p>
      <ol class="workflow-card__steps">
        <li v-for="(step, i) in wf.steps" :key="i">
          <span class="workflow-card__idx">{{ i + 1 }}</span>
          {{ step.label }}
        </li>
      </ol>
      <el-button type="primary" plain class="workflow-card__cta" @click="start(wf.ctaRoute)">
        {{ wf.ctaLabel }}
        <el-icon class="workflow-card__arrow"><ArrowRight /></el-icon>
      </el-button>
    </article>
  </div>
</template>

<style scoped lang="scss">
.workflow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
}

.workflow-card {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  padding: 1.15rem 1.2rem 1.2rem;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  transition: transform 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.07);
  }

  h3 {
    margin: 0;
    font-size: 1.02rem;
    color: var(--title);
    letter-spacing: -0.02em;
  }

  > p {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.6;
    color: var(--muted);
    flex: 1;
  }

  &--teal {
    border-top: 3px solid var(--bio-green);
  }
  &--blue {
    border-top: 3px solid var(--bio-blue);
  }
  &--cyan {
    border-top: 3px solid #0d9488;
  }
  &--violet {
    border-top: 3px solid #7c3aed;
  }
}

.workflow-card__steps {
  list-style: none;
  margin: 0.15rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;

  li {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: var(--body);
  }
}

.workflow-card__idx {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--bio-green-dark);
  background: var(--bio-green-light);
}

.workflow-card__cta {
  align-self: flex-start;
  margin-top: 0.25rem;
}

.workflow-card__arrow {
  margin-left: 0.25rem;
}
</style>
