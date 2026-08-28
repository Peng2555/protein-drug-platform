<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import CapabilityMap from '@/components/home/CapabilityMap.vue'
import WorkflowCards from '@/components/home/WorkflowCards.vue'
import {
  SCENARIO_DETAILS,
  WORKFLOWS_BY_SCENARIO,
  MODULE_ENGINES,
  SCENARIO_MODULES,
  scenarioById,
  type ScenarioId,
} from '@/config/workflows'
import { navItemById } from '@/utils/platform'

const route = useRoute()
const router = useRouter()

const scenarioId = computed(() => String(route.params.id || 'vhh') as ScenarioId)
const scenario = computed(() => scenarioById(scenarioId.value))
const detail = computed(() => SCENARIO_DETAILS[scenarioId.value])
const workflows = computed(() => WORKFLOWS_BY_SCENARIO[scenarioId.value] ?? [])

const modules = computed(() =>
  SCENARIO_MODULES[scenarioId.value].map((moduleId) => {
    const item = navItemById(moduleId)
    return {
      moduleId,
      label: item.label,
      path: item.path,
      engine: MODULE_ENGINES[moduleId],
    }
  }),
)

function start(routePath: string) {
  router.push(routePath)
}
</script>

<template>
  <div v-if="scenario" class="use-case">
    <section class="use-case-hero">
      <div class="landing-container use-case-hero__inner">
        <button type="button" class="use-case-back" @click="router.push('/home')">
          <el-icon><ArrowLeft /></el-icon>
          返回首页
        </button>
        <p class="use-case-hero__tag">Use Case</p>
        <h1>{{ scenario.label }}</h1>
        <p class="use-case-hero__lead">{{ detail.intro }}</p>
        <button type="button" class="use-case-hero__cta" @click="start(scenario.primaryCta.route)">
          {{ scenario.primaryCta.label }}
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </section>

    <section class="landing-section">
      <div class="landing-container">
        <div class="landing-section__head landing-section__head--left">
          <h2>推荐流程</h2>
          <p>{{ scenario.summary }}</p>
        </div>
        <div class="pipeline">
          <article v-for="(step, i) in scenario.pipeline" :key="step.title" class="pipeline-step">
            <span class="pipeline-step__num">{{ i + 1 }}</span>
            <div>
              <h3>{{ step.title }}</h3>
              <p>{{ step.description }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="landing-section landing-section--soft">
      <div class="landing-container">
        <div class="landing-section__head landing-section__head--left">
          <h2>工作流入口</h2>
        </div>
        <WorkflowCards :workflows="workflows" />
      </div>
    </section>

    <section class="landing-section">
      <div class="landing-container">
        <div class="landing-section__head landing-section__head--left">
          <h2>典型输出</h2>
        </div>
        <div class="outputs">
          <span v-for="o in detail.outputs" :key="o" class="output-chip">{{ o }}</span>
        </div>
        <div class="landing-section__head landing-section__head--left" style="margin-top: 2rem">
          <h2>相关模块</h2>
        </div>
        <div class="module-row">
          <button
            v-for="m in modules"
            :key="m.moduleId"
            type="button"
            class="module-pill"
            @click="start(`${m.path}/new`)"
          >
            <strong>{{ m.label }}</strong>
            <span>{{ m.engine }}</span>
          </button>
        </div>
      </div>
    </section>

    <section class="landing-section landing-section--soft">
      <div class="landing-container">
        <CapabilityMap :scenario="scenarioId" />
      </div>
    </section>
  </div>
  <div v-else class="landing-container" style="padding: 3rem 0">
    <el-empty description="未找到该场景">
      <el-button type="primary" @click="router.push('/home')">回首页</el-button>
    </el-empty>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/home-landing.scss';

.use-case-hero {
  padding: 2.5rem 0 3rem;
  background: linear-gradient(135deg, #004d47 0%, #1a4a8a 100%);
  color: #fff;
}

.use-case-hero__inner {
  max-width: 720px;
}

.use-case-back {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1.25rem;
  padding: 0.35rem 0.65rem;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-size: 0.8rem;
  cursor: pointer;
}

.use-case-hero__tag {
  margin: 0 0 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.75;
}

h1 {
  margin: 0;
  font-size: clamp(1.75rem, 3vw, 2.35rem);
  letter-spacing: -0.03em;
}

.use-case-hero__lead {
  margin: 1rem 0 0;
  font-size: 1rem;
  line-height: 1.7;
  opacity: 0.9;
}

.use-case-hero__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1.5rem;
  padding: 0.7rem 1.3rem;
  border: none;
  border-radius: 999px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  color: #0a4a45;
  background: #fff;
}

.pipeline {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
}

.pipeline-step {
  display: flex;
  gap: 0.85rem;
  padding: 1.1rem 1.15rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fff;

  h3 {
    margin: 0;
    font-size: 0.92rem;
    color: var(--title);
  }

  p {
    margin: 0.35rem 0 0;
    font-size: 0.8rem;
    line-height: 1.55;
    color: var(--muted);
  }
}

.pipeline-step__num {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 0.78rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
}

.outputs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.output-chip {
  padding: 0.45rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-family: var(--mono);
  color: var(--bio-blue-dark);
  background: var(--bio-blue-light);
  border: 1px solid rgba(46, 90, 165, 0.15);
}

.module-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}

.module-pill {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.15rem;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.35);
    box-shadow: var(--shadow);
  }

  strong {
    font-size: 0.88rem;
    color: var(--title);
  }

  span {
    font-size: 0.72rem;
    color: var(--bio-green-dark);
  }
}

.landing-section__head--left {
  text-align: left;
  margin-left: 0;
  margin-right: 0;
  max-width: none;
}
</style>
