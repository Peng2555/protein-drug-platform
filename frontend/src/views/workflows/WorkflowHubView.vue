<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import PipelineWorkflowCard from '@/components/workflows/PipelineWorkflowCard.vue'
import WorkflowCards from '@/components/home/WorkflowCards.vue'
import {
  PIPELINE_SCENE_TABS,
  pipelinesForScene,
  type PipelineSceneId,
} from '@/config/pipelineWorkflows'
import { WORKFLOWS_BY_SCENARIO, type ScenarioId } from '@/config/workflows'

const route = useRoute()
const router = useRouter()

const query = ref('')
const activeScene = ref<PipelineSceneId>('all')

/** 场景 Tab → 首页 workflows 配置映射（单步快捷入口） */
const sceneToWorkflowScenario: Partial<Record<PipelineSceneId, ScenarioId>> = {
  antibody: 'antibody',
  peptide: 'general',
  small_molecule: 'small_molecule',
  general: 'general',
}

watch(
  () => route.query.scene,
  (s) => {
    if (typeof s === 'string' && PIPELINE_SCENE_TABS.some((t) => t.id === s)) {
      activeScene.value = s as PipelineSceneId
    }
  },
  { immediate: true },
)

function setScene(id: PipelineSceneId) {
  activeScene.value = id
  router.replace({ query: id === 'all' ? {} : { scene: id } })
}

const pipelines = computed(() => {
  const list = pipelinesForScene(activeScene.value)
  const q = query.value.trim().toLowerCase()
  if (!q) return list
  return list.filter((p) =>
    [p.title, p.description, ...p.steps.map((s) => s.label)].join(' ').toLowerCase().includes(q),
  )
})

const quickWorkflows = computed(() => {
  const scenario = sceneToWorkflowScenario[activeScene.value]
  if (!scenario) return []
  return WORKFLOWS_BY_SCENARIO[scenario] ?? []
})

const showQuickTools = computed(
  () => activeScene.value !== 'all' && quickWorkflows.value.length > 0,
)
</script>

<template>
  <div class="workflow-hub">
    <header class="workflow-hub__head">
      <h1>工作流</h1>
      <p>按研发场景选择可执行流水线，或从下方单步工具单独提交任务。</p>
    </header>

    <div class="workflow-hub__scenes">
      <span class="workflow-hub__scene-label">场景</span>
      <div class="workflow-hub__scene-pills">
        <button
          v-for="tab in PIPELINE_SCENE_TABS"
          :key="tab.id"
          type="button"
          class="scene-pill"
          :class="{ active: activeScene === tab.id }"
          @click="setScene(tab.id)"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div class="workflow-hub__toolbar">
      <div class="workflow-hub__search">
        <el-icon><Search /></el-icon>
        <input
          v-model="query"
          type="search"
          placeholder="搜索流水线…"
          aria-label="搜索流水线"
        />
      </div>
    </div>

    <section class="workflow-hub__section">
      <h2 class="workflow-hub__section-title">可执行流水线</h2>
      <div v-if="pipelines.length" class="workflow-hub__grid">
        <PipelineWorkflowCard v-for="p in pipelines" :key="p.id" :pipeline="p" />
      </div>
      <p v-else class="workflow-hub__empty">
        该场景暂无流水线模板，可先从下方单步工具开始，或切换其他场景 Tab。
      </p>
    </section>

    <section v-if="showQuickTools" class="workflow-hub__section workflow-hub__section--secondary">
      <h2 class="workflow-hub__section-title">相关单步工具</h2>
      <p class="workflow-hub__section-desc">尚未接入流水线编排的原子模块，可单独提交任务。</p>
      <WorkflowCards :workflows="quickWorkflows" />
    </section>
  </div>
</template>

<style scoped lang="scss">
.workflow-hub {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.5rem 0 2rem;
}

.workflow-hub__head {
  margin-bottom: 1.75rem;

  h1 {
    margin: 0;
    font-size: clamp(1.5rem, 2.5vw, 1.85rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #111827;
  }

  p {
    margin: 0.45rem 0 0;
    font-size: 0.9rem;
    color: #6b7280;
  }
}

.workflow-hub__scenes {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}

.workflow-hub__scene-label {
  flex-shrink: 0;
  width: 2.5rem;
  padding-top: 0.35rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #9ca3af;
}

.workflow-hub__scene-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.scene-pill {
  padding: 0.38rem 0.85rem;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #4b5563;
  background: #f9fafb;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;

  &:hover {
    background: #f3f4f6;
  }

  &.active {
    color: #fff;
    background: linear-gradient(135deg, var(--bio-green, #00aca1), var(--bio-blue, #2563eb));
    border-color: transparent;
    box-shadow: 0 4px 12px rgba(0, 122, 114, 0.2);
  }
}

.workflow-hub__toolbar {
  margin-bottom: 1.5rem;
}

.workflow-hub__search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  max-width: 360px;
  padding: 0.55rem 0.85rem;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  color: #9ca3af;

  input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 0.88rem;
    color: #111827;
    background: transparent;

    &::placeholder {
      color: #9ca3af;
    }
  }
}

.workflow-hub__section {
  margin-bottom: 2rem;
}

.workflow-hub__section--secondary {
  padding-top: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

.workflow-hub__section-title {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 700;
  color: #111827;
}

.workflow-hub__section-desc {
  margin: -0.5rem 0 1rem;
  font-size: 0.82rem;
  color: #9ca3af;
}

.workflow-hub__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 1rem;
}

.workflow-hub__empty {
  margin: 1rem 0;
  padding: 2rem;
  text-align: center;
  font-size: 0.88rem;
  color: #9ca3af;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px dashed #e5e7eb;
}
</style>
