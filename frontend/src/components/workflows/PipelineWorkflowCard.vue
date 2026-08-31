<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import type { PipelineWorkflowDef } from '@/config/pipelineWorkflows'

defineProps<{
  pipeline: PipelineWorkflowDef
}>()

const router = useRouter()

function openDetail(id: string) {
  if (id === 'affinity-maturation') {
    router.push({ name: 'affinity-redesign-new' })
    return
  }
  if (id === 'peptide-target-design') {
    router.push({ name: 'masking-peptide-new' })
    return
  }
  router.push({ name: 'workflow-detail', params: { id } })
}
</script>

<template>
  <article class="pipeline-card" :class="`pipeline-card--${pipeline.accent}`">
    <div class="pipeline-card__head">
      <span class="pipeline-card__badge">流水线</span>
      <span v-if="pipeline.status === 'placeholder'" class="pipeline-card__status">占位</span>
      <span v-else-if="pipeline.status === 'beta'" class="pipeline-card__status pipeline-card__status--beta">已接入</span>
    </div>
    <h3>{{ pipeline.title }}</h3>
    <p>{{ pipeline.description }}</p>
    <ol class="pipeline-card__steps">
      <li v-for="(step, i) in pipeline.steps" :key="step.id">
        <span class="pipeline-card__idx">{{ i + 1 }}</span>
        {{ step.label }}
      </li>
    </ol>
    <p class="pipeline-card__duration">{{ pipeline.estimatedDuration }}</p>
    <el-button type="primary" plain class="pipeline-card__cta" @click="openDetail(pipeline.id)">
      {{ pipeline.status === 'beta' ? '开始任务' : '查看流水线' }}
      <el-icon class="pipeline-card__arrow"><ArrowRight /></el-icon>
    </el-button>
  </article>
</template>

<style scoped lang="scss">
.pipeline-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.35rem 1.4rem 1.45rem;
  border-radius: 18px;
  border: 1px solid #e5e7eb;
  background: #fff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.07);
  }

  h3 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 700;
    color: #111827;
    letter-spacing: -0.02em;
  }

  > p {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.6;
    color: #6b7280;
    flex: 1;
  }

  &--teal {
    border-top: 3px solid var(--bio-green, #00aca1);
  }
  &--blue {
    border-top: 3px solid var(--bio-blue, #2563eb);
  }
  &--cyan {
    border-top: 3px solid #0d9488;
  }
  &--violet {
    border-top: 3px solid #7c3aed;
  }
}

.pipeline-card__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pipeline-card__badge {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #0f766e;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.pipeline-card__status {
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 600;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;

  &--beta {
    color: #065f46;
    background: #ecfdf5;
    border-color: #a7f3d0;
  }
}

.pipeline-card__steps {
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
    color: #374151;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
  }
}

.pipeline-card__idx {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.62rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green, #00aca1), var(--bio-blue, #2563eb));
}

.pipeline-card__duration {
  margin: 0;
  font-size: 0.75rem;
  color: #9ca3af;
}

.pipeline-card__cta {
  align-self: flex-start;
  margin-top: 0.25rem;
}

.pipeline-card__arrow {
  margin-left: 0.25rem;
}
</style>
