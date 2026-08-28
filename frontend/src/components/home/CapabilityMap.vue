<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { MODULE_ENGINES, SCENARIO_MODULES, type ScenarioId } from '@/config/workflows'
import { ALL_NAV_ITEMS, type ModuleId } from '@/utils/platform'

const props = defineProps<{
  scenario: ScenarioId
}>()

const router = useRouter()
const query = ref('')
const category = ref<'all' | 'structure' | 'sequence' | 'ligand'>('all')

const CATEGORY_MODULES: Record<'structure' | 'sequence' | 'ligand', ModuleId[]> = {
  structure: ['fold'],
  sequence: ['design', 'rosetta', 'developability', 'maturation', 'synthesis'],
  ligand: ['docking', 'md'],
}

const items = computed(() => {
  const scenarioSet = new Set(SCENARIO_MODULES[props.scenario])
  let list = ALL_NAV_ITEMS.filter((item) => item.id !== 'home')

  if (category.value !== 'all') {
    const catSet = new Set(CATEGORY_MODULES[category.value])
    list = list.filter((item) => catSet.has(item.id))
  } else {
    list = list.filter((item) => scenarioSet.has(item.id))
  }

  const q = query.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.hint.toLowerCase().includes(q) ||
        (MODULE_ENGINES[item.id] ?? '').toLowerCase().includes(q),
    )
  }

  return list
})

function openModule(path: string) {
  router.push(`${path}/new`)
}
</script>

<template>
  <div class="capability-map">
    <div class="capability-map__toolbar">
      <el-input
        v-model="query"
        placeholder="搜索能力，如 Rosetta、对接、MD…"
        clearable
        class="capability-map__search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <div class="capability-map__filters">
        <button
          v-for="f in [
            { id: 'all', label: '本场景' },
            { id: 'structure', label: '结构' },
            { id: 'sequence', label: '序列' },
            { id: 'ligand', label: '小分子' },
          ]"
          :key="f.id"
          type="button"
          class="cap-filter"
          :class="{ 'cap-filter--active': category === f.id }"
          @click="category = f.id as typeof category"
        >
          {{ f.label }}
        </button>
      </div>
    </div>

    <div v-if="items.length" class="capability-map__grid">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="cap-card"
        @click="openModule(item.path)"
      >
        <div class="cap-card__head">
          <strong>{{ item.label }}</strong>
          <span v-if="MODULE_ENGINES[item.id]" class="cap-card__engine">{{ MODULE_ENGINES[item.id] }}</span>
        </div>
        <p>{{ item.hint }}</p>
        <span class="cap-card__link">进入模块 →</span>
      </button>
    </div>
    <el-empty v-else description="没有匹配的能力模块" :image-size="72" />
  </div>
</template>

<style scoped lang="scss">
.capability-map__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
}

.capability-map__search {
  max-width: 320px;
  flex: 1;
  min-width: 200px;
}

.capability-map__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.cap-filter {
  padding: 0.32rem 0.72rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 0.76rem;
  color: var(--body);
  cursor: pointer;

  &--active,
  &:hover {
    border-color: rgba(46, 90, 165, 0.35);
    color: var(--bio-blue-dark);
    background: var(--bio-blue-light);
  }
}

.capability-map__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.cap-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.95rem 1rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.15s,
    transform 0.15s,
    box-shadow 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.35);
    transform: translateY(-1px);
    box-shadow: var(--shadow);
  }

  p {
    margin: 0;
    font-size: 0.76rem;
    line-height: 1.5;
    color: var(--muted);
    flex: 1;
  }
}

.cap-card__head {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.cap-card__head strong {
  font-size: 0.9rem;
  color: var(--title);
}

.cap-card__engine {
  font-size: 0.68rem;
  color: var(--bio-green-dark);
  font-weight: 600;
}

.cap-card__link {
  font-size: 0.72rem;
  color: var(--bio-blue);
  font-weight: 600;
}
</style>
