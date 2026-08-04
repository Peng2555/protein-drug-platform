<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiJson } from '@/api/client'
import InterfaceViewer3d from '@/components/structure/InterfaceViewer3d.vue'
import { IX_TYPE_LABELS } from '@/types/structure'
import type {
  InteractionFilter,
  InterfaceInteraction,
  JobInterfaceData,
} from '@/types/structure'

export type { JobInterfaceData, InteractionFilter } from '@/types/structure'

const props = withDefaults(
  defineProps<{
    jobId: string
    cifText?: string | null
    /** When provided, skips API fetch. */
    interfaceData?: JobInterfaceData | null
    loading?: boolean
    error?: string | null
    /** Minimum chain count to show section (legacy: 2). */
    minChains?: number
    chainCount?: number
  }>(),
  {
    cifText: null,
    interfaceData: null,
    loading: false,
    error: null,
    minChains: 2,
    chainCount: 2,
  },
)

const emit = defineEmits<{
  loaded: [data: JobInterfaceData]
  error: [message: string]
}>()

const viewerRef = ref<InstanceType<typeof InterfaceViewer3d> | null>(null)
const internalLoading = ref(false)
const internalError = ref('')
const data = ref<JobInterfaceData | null>(props.interfaceData)
const ixFilter = ref<InteractionFilter>('all')
const activeRowIndex = ref<number | null>(null)

const isLoading = computed(() => props.loading || internalLoading.value)
const errorMessage = computed(() => props.error || internalError.value)

const primary = computed(() => data.value?.primary_interface ?? null)

const methodText = computed(() => {
  if (!data.value || !primary.value) return ''
  return (
    data.value.method ||
    `${primary.value.label_a} ↔ ${primary.value.label_b} · 非共价相互作用分析`
  )
})

const summaryStats = computed(() => {
  const p = primary.value
  if (!p) return []
  const ixSum = p.interaction_summary || {}
  const extraIx =
    (ixSum.n_pi_stacking ?? 0) + (ixSum.n_water_bridges ?? 0) + (ixSum.n_polar_contacts ?? 0)
  return [
    { label: 'pDockQ', value: p.pdockq?.toFixed(3) ?? '—' },
    {
      label: 'PLIP 相互作用',
      value: String(ixSum.n_total ?? p.interactions?.length ?? 0),
    },
    { label: '氢键', value: String(ixSum.n_hbonds ?? 0) },
    { label: '盐桥', value: String(ixSum.n_salt_bridges ?? 0) },
    { label: '疏水', value: String(ixSum.n_hydrophobic ?? 0) },
    { label: 'π/水桥等', value: String(extraIx) },
    {
      label: `${p.label_a || p.chain_a} 界面残基`,
      value: String(p.residues_a?.length || 0),
    },
    {
      label: `${p.label_b || p.chain_b} 界面残基`,
      value: String(p.residues_b?.length || 0),
    },
  ]
})

const interactionCounts = computed(() => {
  const interactions = primary.value?.interactions || []
  const counts: Record<string, number> = { all: interactions.length }
  for (const ix of interactions) {
    counts[ix.type] = (counts[ix.type] || 0) + 1
  }
  return counts
})

const filterOptions = computed(() => {
  const counts = interactionCounts.value
  const types = ['all', ...Object.keys(IX_TYPE_LABELS).filter((t) => counts[t])]
  return types.map((t) => ({
    value: t as InteractionFilter,
    label:
      t === 'all'
        ? `全部 (${counts.all})`
        : `${IX_TYPE_LABELS[t]} (${counts[t]})`,
  }))
})

const filteredInteractions = computed(() => {
  const interactions = primary.value?.interactions || []
  if (ixFilter.value === 'all') return interactions
  return interactions.filter((ix) => ix.type === ixFilter.value)
})

const showSection = computed(() => props.chainCount >= props.minChains)

const hasContent = computed(
  () => !!primary.value?.contact_pairs && !errorMessage.value && !isLoading.value,
)

async function fetchInterface(): Promise<void> {
  if (props.interfaceData) {
    data.value = props.interfaceData
    return
  }
  if (!props.jobId) return

  internalLoading.value = true
  internalError.value = ''
  try {
    const result = await apiJson<JobInterfaceData>(`/api/jobs/${props.jobId}/interface`)
    data.value = result
    emit('loaded', result)
  } catch (e) {
    const message = e instanceof Error ? e.message : '结合界面加载失败'
    internalError.value = message
    data.value = null
    emit('error', message)
  } finally {
    internalLoading.value = false
  }
}

function setFilter(filter: InteractionFilter): void {
  ixFilter.value = filter
  activeRowIndex.value = null
}

function onRowClick(ix: InterfaceInteraction, index: number): void {
  activeRowIndex.value = index
  viewerRef.value?.focusInteraction(ix)
}

function interactionTypeLabel(type: string): string {
  return IX_TYPE_LABELS[type] || type
}

watch(
  () => [props.jobId, props.interfaceData] as const,
  () => {
    ixFilter.value = 'all'
    activeRowIndex.value = null
    void fetchInterface()
  },
  { immediate: true, deep: true },
)

watch(
  () => props.interfaceData,
  (val) => {
    if (val) data.value = val
  },
)
</script>

<template>
  <section v-if="showSection" class="interface-panel">
    <div class="interface-panel__head">
      <h3>结合界面 · PLIP</h3>
    </div>

    <div v-if="isLoading" v-loading="true" class="interface-panel__loading">
      正在分析结合界面…
    </div>

    <el-alert
      v-else-if="errorMessage"
      type="error"
      :closable="false"
      show-icon
      :title="errorMessage"
    />

    <template v-else-if="data?.error">
      <el-alert type="warning" :closable="false" show-icon :title="data.error" />
    </template>

    <template v-else-if="!primary?.contact_pairs">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="未检测到链间接触（可能为单链或链间距过大）"
      />
    </template>

    <div v-else-if="hasContent" class="interface-panel__content">
      <p v-if="methodText" class="interface-panel__method">{{ methodText }}</p>

      <div class="interface-summary">
        <div v-for="stat in summaryStats" :key="stat.label" class="interface-stat">
          <div class="val">{{ stat.value }}</div>
          <div class="lbl">{{ stat.label }}</div>
        </div>
      </div>

      <InterfaceViewer3d
        v-if="cifText"
        ref="viewerRef"
        :cif-text="cifText"
        :data="data!"
        :primary="primary"
      />

      <div class="interface-interaction-panel">
        <h4>PLIP 相互作用</h4>

        <div class="interaction-filters">
          <el-button
            v-for="opt in filterOptions"
            :key="opt.value"
            size="small"
            round
            :type="ixFilter === opt.value ? 'primary' : 'default'"
            plain
            @click="setFilter(opt.value)"
          >
            {{ opt.label }}
          </el-button>
        </div>

        <div v-if="!filteredInteractions.length" class="interaction-empty">
          暂无该类相互作用
        </div>

        <div v-else class="interaction-table-wrap">
          <el-table
            :data="filteredInteractions"
            size="small"
            stripe
            highlight-current-row
            :current-row-key="activeRowIndex ?? undefined"
            @row-click="(row) => onRowClick(row, filteredInteractions.indexOf(row))"
          >
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="
                    row.type === 'salt_bridge'
                      ? 'danger'
                      : row.type === 'hbond'
                        ? 'warning'
                        : 'info'
                  "
                  effect="plain"
                  class="ix-type-pill"
                >
                  {{ interactionTypeLabel(row.type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="受体/链 A" min-width="120">
              <template #default="{ row }">
                {{ row.resname_a }} {{ row.chain_a }}{{ row.resnum_a }}
              </template>
            </el-table-column>
            <el-table-column label="抗体/链 B" min-width="120">
              <template #default="{ row }">
                {{ row.resname_b }} {{ row.chain_b }}{{ row.resnum_b }}
              </template>
            </el-table-column>
            <el-table-column label="距离 (Å)" width="90" align="right">
              <template #default="{ row }">
                {{ row.distance_angstrom.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column label="详情" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.detail || `${row.atom_a} ↔ ${row.atom_b}` }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div v-if="data?.reference_tools?.length" class="interface-ref-tools">
        参考工具：
        <el-link
          v-for="tool in data.reference_tools"
          :key="tool.url"
          :href="tool.url"
          target="_blank"
          type="primary"
        >
          {{ tool.name }}
        </el-link>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.interface-panel {
  margin-top: 1.25rem;

  &__head h3 {
    margin: 0 0 0.75rem;
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--title);
  }

  &__loading {
    min-height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 0.88rem;
  }

  &__method {
    margin: 0 0 0.75rem;
    font-size: 0.82rem;
    color: var(--muted);
  }

  &__content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
}

.interface-summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 0.5rem;
}

.interface-stat {
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;

  .val {
    font-size: 1rem;
    font-weight: 700;
    color: var(--title);
  }

  .lbl {
    margin-top: 0.15rem;
    font-size: 0.68rem;
    color: var(--muted);
  }
}

.interface-interaction-panel h4 {
  margin: 0 0 0.45rem;
  font-size: 0.9rem;
  color: var(--title);
}

.interaction-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.interaction-empty {
  padding: 0.75rem;
  font-size: 0.85rem;
  color: var(--muted);
}

.interaction-table-wrap {
  max-height: 280px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
}

.interface-ref-tools {
  font-size: 0.78rem;
  color: var(--muted);

  :deep(.el-link) {
    margin-right: 0.35rem;
  }
}
</style>
