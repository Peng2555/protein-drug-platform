<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import ToolCatalogCard from '@/components/app/ToolCatalogCard.vue'
import {
  PLATFORM_TOOLS,
  TOOL_FUNCTION_LABELS,
  TOOL_INPUT_LABELS,
  TOOL_MODALITY_LABELS,
  type PlatformTool,
  type ToolFunction,
  type ToolInput,
  type ToolModality,
} from '@/config/tools'

type TabId = 'all' | 'new'

const query = ref('')
const activeTab = ref<TabId>('all')
const modality = ref<ToolModality | 'all'>('all')
const fn = ref<ToolFunction | 'all'>('all')
const input = ref<ToolInput | 'all'>('all')

const modalityOptions = Object.entries(TOOL_MODALITY_LABELS) as [ToolModality, string][]
const functionOptions = Object.entries(TOOL_FUNCTION_LABELS) as [ToolFunction, string][]
const inputOptions = Object.entries(TOOL_INPUT_LABELS) as [ToolInput, string][]

function matches(tool: PlatformTool): boolean {
  const q = query.value.trim().toLowerCase()
  if (q) {
    const hay = [
      tool.name,
      tool.description,
      tool.citation ?? '',
      TOOL_FUNCTION_LABELS[tool.function],
      ...tool.modalities.map((m) => TOOL_MODALITY_LABELS[m]),
    ]
      .join(' ')
      .toLowerCase()
    if (!hay.includes(q)) return false
  }
  if (activeTab.value === 'new' && !tool.isNew) return false
  if (modality.value !== 'all' && !tool.modalities.includes(modality.value)) return false
  if (fn.value !== 'all' && tool.function !== fn.value) return false
  if (input.value !== 'all' && !tool.inputs.includes(input.value)) return false
  return true
}

const filtered = computed(() => PLATFORM_TOOLS.filter(matches))
</script>

<template>
  <div class="app-tools">
    <header class="app-tools__head">
      <h1>计算工具</h1>
      <p>选择模块提交任务——无需部署，内网 GPU 自动调度。</p>
    </header>

    <div class="app-tools__filters">
      <div class="filter-row">
        <span class="filter-label">模态</span>
        <div class="filter-pills">
          <button
            type="button"
            class="filter-pill"
            :class="{ active: modality === 'all' }"
            @click="modality = 'all'"
          >
            全部
          </button>
          <button
            v-for="[id, label] in modalityOptions"
            :key="id"
            type="button"
            class="filter-pill"
            :class="{ active: modality === id }"
            @click="modality = id"
          >
            {{ label }}
          </button>
        </div>
      </div>

      <div class="filter-row">
        <span class="filter-label">功能</span>
        <div class="filter-pills">
          <button
            type="button"
            class="filter-pill"
            :class="{ active: fn === 'all' }"
            @click="fn = 'all'"
          >
            全部
          </button>
          <button
            v-for="[id, label] in functionOptions"
            :key="id"
            type="button"
            class="filter-pill"
            :class="{ active: fn === id }"
            @click="fn = id"
          >
            {{ label }}
          </button>
        </div>
      </div>

      <div class="filter-row">
        <span class="filter-label">输入</span>
        <div class="filter-pills">
          <button
            type="button"
            class="filter-pill"
            :class="{ active: input === 'all' }"
            @click="input = 'all'"
          >
            全部
          </button>
          <button
            v-for="[id, label] in inputOptions"
            :key="id"
            type="button"
            class="filter-pill"
            :class="{ active: input === id }"
            @click="input = id"
          >
            {{ label }}
          </button>
        </div>
      </div>
    </div>

    <div class="app-tools__toolbar">
      <div class="app-tools__search">
        <el-icon><Search /></el-icon>
        <input
          v-model="query"
          type="search"
          placeholder="搜索工具…"
          aria-label="搜索工具"
        />
      </div>
      <div class="app-tools__tabs">
        <button
          type="button"
          class="app-tools__tab"
          :class="{ active: activeTab === 'all' }"
          @click="activeTab = 'all'"
        >
          全部
        </button>
        <button
          type="button"
          class="app-tools__tab"
          :class="{ active: activeTab === 'new' }"
          @click="activeTab = 'new'"
        >
          New
        </button>
      </div>
    </div>

    <div v-if="filtered.length" class="app-tools__grid">
      <ToolCatalogCard v-for="tool in filtered" :key="tool.id" :tool="tool" />
    </div>
    <p v-else class="app-tools__empty">没有匹配的工具，试试调整筛选或搜索词。</p>
  </div>
</template>

<style scoped lang="scss">
.app-tools {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.5rem 0 2rem;
}

.app-tools__head {
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

.app-tools__filters {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}

.filter-row {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  flex-wrap: wrap;
}

.filter-label {
  flex-shrink: 0;
  width: 2.5rem;
  padding-top: 0.35rem;
  font-size: 0.78rem;
  font-weight: 700;
  color: #9ca3af;
}

.filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.filter-pill {
  padding: 0.38rem 0.75rem;
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
    color: #111827;
    background: #fff;
    border-color: #111827;
  }
}

.app-tools__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
}

.app-tools__search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 200px;
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

.app-tools__tabs {
  display: flex;
  gap: 0.35rem;
  padding: 0.2rem;
  border-radius: 999px;
  background: #f3f4f6;
}

.app-tools__tab {
  padding: 0.45rem 1rem;
  border: none;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #6b7280;
  background: transparent;
  cursor: pointer;

  &.active {
    color: #111827;
    background: #fff;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
  }
}

.app-tools__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 1rem;
}

.app-tools__empty {
  margin: 2rem 0;
  text-align: center;
  font-size: 0.9rem;
  color: #9ca3af;
}
</style>
