<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { pipelineById } from '@/config/pipelineWorkflows'
import { MODULE_ENGINES } from '@/config/workflows'

const route = useRoute()
const router = useRouter()

const pipelineId = computed(() => route.params.id as string)
const pipeline = computed(() => pipelineById(pipelineId.value))

const form = reactive<Record<string, string>>({})

function goBack() {
  const scene = pipeline.value?.scene
  router.push(scene ? { name: 'workflows', query: { scene } } : { name: 'workflows' })
}

function openStep(route: string) {
  router.push(route)
}

function submitPipeline() {
  ElMessage.info('流水线编排开发中：当前为占位界面，后续接入脚本后可一键提交。')
}

watch(
  pipeline,
  (p) => {
    if (p?.id === 'affinity-maturation') {
      router.replace({ name: 'affinity-redesign-new' })
      return
    }
    if (p?.id === 'peptide-target-design') {
      router.replace({ name: 'masking-peptide-new' })
      return
    }
    if (!p) router.replace({ name: 'workflows' })
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="pipeline" class="workflow-detail">
    <button type="button" class="workflow-detail__back" @click="goBack">
      <el-icon><ArrowLeft /></el-icon>
      返回工作流
    </button>

    <header class="workflow-detail__head page-card">
      <div class="workflow-detail__head-top">
        <span class="workflow-detail__badge">流水线</span>
        <span class="workflow-detail__status">占位 · 脚本编排接入中</span>
      </div>
      <h1>{{ pipeline.title }}</h1>
      <p>{{ pipeline.description }}</p>
      <p class="workflow-detail__meta">预计耗时：{{ pipeline.estimatedDuration }}</p>
    </header>

    <section class="workflow-detail__steps page-card">
      <h2>流水线步骤</h2>
      <ol class="step-list">
        <li v-for="(step, i) in pipeline.steps" :key="step.id" class="step-item">
          <div class="step-item__marker">
            <span class="step-item__num">{{ i + 1 }}</span>
            <span v-if="i < pipeline.steps.length - 1" class="step-item__line" />
          </div>
          <div class="step-item__body">
            <div class="step-item__title-row">
              <h3>{{ step.label }}</h3>
              <span v-if="step.moduleId && MODULE_ENGINES[step.moduleId]" class="step-item__engine">
                {{ MODULE_ENGINES[step.moduleId] }}
              </span>
            </div>
            <p>{{ step.description }}</p>
            <button
              v-if="step.moduleRoute"
              type="button"
              class="step-item__link"
              @click="openStep(step.moduleRoute!)"
            >
              单独运行此步骤
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </li>
      </ol>
    </section>

    <section class="workflow-detail__input page-card">
      <h2>统一输入</h2>
      <p class="workflow-detail__input-hint">
        <el-icon><InfoFilled /></el-icon>
        {{ pipeline.inputHint }}
      </p>
      <form class="input-form" @submit.prevent="submitPipeline">
        <label v-for="field in pipeline.inputFields" :key="field.key" class="input-form__field">
          <span>
            {{ field.label }}
            <em v-if="field.required">*</em>
          </span>
          <textarea
            v-if="field.key.includes('fasta')"
            v-model="form[field.key]"
            rows="4"
            :placeholder="field.placeholder"
          />
          <input
            v-else
            v-model="form[field.key]"
            type="text"
            :placeholder="field.placeholder"
          />
        </label>
        <div class="input-form__actions">
          <el-button type="primary" size="large" disabled @click="submitPipeline">
            提交流水线（开发中）
          </el-button>
          <span class="input-form__note">占位表单，数据不会提交；可先通过上方「单独运行此步骤」使用各模块。</span>
        </div>
      </form>
    </section>

    <section class="workflow-detail__runs page-card">
      <h2>流水线任务</h2>
      <el-empty description="暂无流水线任务记录" />
    </section>
  </div>
</template>

<style scoped lang="scss">
.workflow-detail {
  max-width: 920px;
  margin: 0 auto;
  padding: 0.5rem 0 2.5rem;
}

.workflow-detail__back {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1rem;
  padding: 0.35rem 0.5rem;
  border: none;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #6b7280;
  background: transparent;
  cursor: pointer;

  &:hover {
    color: #111827;
    background: #f3f4f6;
  }
}

.workflow-detail__head {
  padding: 1.75rem 2rem;
  margin-bottom: 1.25rem;
}

.workflow-detail__head-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.workflow-detail__badge {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #0f766e;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.workflow-detail__status {
  font-size: 0.75rem;
  color: #92400e;
}

h1 {
  margin: 0 0 0.5rem;
  font-size: clamp(1.35rem, 2.5vw, 1.65rem);
  font-weight: 800;
  color: #111827;
  letter-spacing: -0.03em;
}

.workflow-detail__head > p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.65;
  color: #4b5563;
}

.workflow-detail__meta {
  margin-top: 0.75rem !important;
  font-size: 0.78rem !important;
  color: #9ca3af !important;
}

.workflow-detail__steps,
.workflow-detail__input,
.workflow-detail__runs {
  padding: 1.5rem 2rem;
  margin-bottom: 1.25rem;
}

h2 {
  margin: 0 0 1.25rem;
  font-size: 1rem;
  font-weight: 700;
  color: #111827;
}

.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.step-item {
  display: flex;
  gap: 1rem;
}

.step-item__marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 32px;
}

.step-item__num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.82rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green, #00aca1), var(--bio-blue, #2563eb));
}

.step-item__line {
  flex: 1;
  width: 2px;
  min-height: 24px;
  margin: 4px 0;
  background: #e5e7eb;
}

.step-item__body {
  flex: 1;
  padding-bottom: 1.5rem;
}

.step-item:last-child .step-item__body {
  padding-bottom: 0;
}

.step-item__title-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;

  h3 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 700;
    color: #111827;
  }
}

.step-item__engine {
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 600;
  color: #6b7280;
  background: #f3f4f6;
}

.step-item__body > p {
  margin: 0 0 0.5rem;
  font-size: 0.82rem;
  line-height: 1.6;
  color: #6b7280;
}

.step-item__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  border: none;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--bio-green-dark, #0f766e);
  background: transparent;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

.workflow-detail__input-hint {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: -0.5rem 0 1.25rem;
  padding: 0.75rem 1rem;
  border-radius: 10px;
  font-size: 0.82rem;
  line-height: 1.55;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.input-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.input-form__field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;

  span {
    font-size: 0.82rem;
    font-weight: 600;
    color: #374151;

    em {
      color: #ef4444;
      font-style: normal;
    }
  }

  input,
  textarea {
    padding: 0.65rem 0.85rem;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    font-size: 0.88rem;
    font-family: inherit;
    color: #111827;
    background: #fff;
    resize: vertical;

    &:focus {
      outline: none;
      border-color: var(--bio-green, #00aca1);
      box-shadow: 0 0 0 3px rgba(0, 172, 161, 0.12);
    }

    &::placeholder {
      color: #9ca3af;
    }
  }
}

.input-form__actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.input-form__note {
  font-size: 0.75rem;
  color: #9ca3af;
}
</style>
