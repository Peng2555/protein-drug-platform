<script setup lang="ts">
import { ArrowRight, Check } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import ScenarioTabs from '@/components/home/ScenarioTabs.vue'
import { SCENARIOS, type ScenarioId } from '@/config/workflows'

const props = defineProps<{
  modelValue: ScenarioId
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ScenarioId]
}>()

const router = useRouter()

const current = computed(
  () => SCENARIOS.find((s) => s.id === props.modelValue) ?? SCENARIOS[0],
)

function start(route: string) {
  router.push(route)
}
</script>

<template>
  <div class="showcase">
    <ScenarioTabs :scenarios="SCENARIOS" :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" />

    <div class="showcase__panel">
      <div class="showcase__copy">
        <p class="showcase__eyebrow">Use Case · {{ current.label }}</p>
        <h2>{{ current.headline }}</h2>
        <p class="showcase__summary">{{ current.summary }}</p>
        <ul class="showcase__list">
          <li v-for="item in current.highlights" :key="item">
            <el-icon><Check /></el-icon>
            {{ item }}
          </li>
        </ul>
        <button type="button" class="showcase__cta" @click="start(current.primaryCta.route)">
          {{ current.primaryCta.label }}
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>

      <div class="showcase__visual" :class="`showcase__visual--${modelValue}`" aria-hidden="true">
        <div class="showcase__visual-inner">
          <span class="showcase__chip">Step 1 · 输入</span>
          <span class="showcase__chip">Step 2 · 计算</span>
          <span class="showcase__chip showcase__chip--active">Step 3 · 结果</span>
          <div class="showcase__flow-line" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.showcase {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.showcase__panel {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(260px, 0.9fr);
  gap: 2rem;
  align-items: center;
  padding: 2rem;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: #fff;
  box-shadow: var(--shadow-md);

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.showcase__eyebrow {
  margin: 0 0 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--bio-green-dark);
}

h2 {
  margin: 0;
  font-size: clamp(1.35rem, 2.2vw, 1.75rem);
  color: var(--title);
  letter-spacing: -0.02em;
}

.showcase__summary {
  margin: 0.75rem 0 0;
  font-size: 0.92rem;
  line-height: 1.7;
  color: var(--body);
}

.showcase__list {
  list-style: none;
  margin: 1.25rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;

  li {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    font-size: 0.86rem;
    color: var(--body);
    line-height: 1.5;

    .el-icon {
      margin-top: 0.15rem;
      color: var(--bio-green);
      flex-shrink: 0;
    }
  }
}

.showcase__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1.5rem;
  padding: 0.65rem 1.2rem;
  border: none;
  border-radius: 999px;
  font-size: 0.88rem;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
  box-shadow: 0 8px 20px rgba(0, 122, 114, 0.25);
  transition: transform 0.15s;

  &:hover {
    transform: translateY(-1px);
  }
}

.showcase__visual {
  min-height: 240px;
  border-radius: 16px;
  padding: 1.25rem;
  position: relative;
  overflow: hidden;

  &--vhh {
    background: linear-gradient(145deg, #e6f7f6, #eef4fc);
  }
  &--antibody {
    background: linear-gradient(145deg, #eef4fc, #f0eefc);
  }
  &--small_molecule {
    background: linear-gradient(145deg, #e8faf8, #e6f2f7);
  }
  &--general {
    background: linear-gradient(145deg, #f3f7fc, #e6f7f6);
  }
}

.showcase__visual-inner {
  position: relative;
  height: 100%;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.85rem;
}

.showcase__chip {
  align-self: flex-start;
  padding: 0.45rem 0.85rem;
  border-radius: 10px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--body);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);

  &--active {
    color: #fff;
    border-color: transparent;
    background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
  }
}

.showcase__flow-line {
  position: absolute;
  left: 1.5rem;
  top: 28%;
  bottom: 28%;
  width: 2px;
  background: linear-gradient(to bottom, var(--bio-green), var(--bio-blue));
  opacity: 0.35;
  border-radius: 2px;
}
</style>
