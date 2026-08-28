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
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.15rem;
}

.workflow-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.35rem 1.4rem 1.45rem;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: #fff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
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
  margin: 0.25rem 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;

  li {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.74rem;
    color: var(--body);
    background: var(--bg-soft);
    border: 1px solid var(--border);
  }
}

.workflow-card__idx {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.62rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
}

.workflow-card__cta {
  align-self: flex-start;
  margin-top: 0.25rem;
}

.workflow-card__arrow {
  margin-left: 0.25rem;
}
</style>
