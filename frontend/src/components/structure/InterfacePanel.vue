<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, apiJson } from '@/api/client'
import InterfaceViewer3d from '@/components/structure/InterfaceViewer3d.vue'
import { IX_LINE_CSS, IX_TYPE_LABELS } from '@/types/structure'
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
    interfaceData?: JobInterfaceData | null
    loading?: boolean
    error?: string | null
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
const internalCifText = ref<string | null>(null)
const data = ref<JobInterfaceData | null>(props.interfaceData)
const ixFilter = ref<InteractionFilter>('all')
const activeRowIndex = ref<number | null>(null)

const isLoading = computed(() => props.loading || internalLoading.value)
const errorMessage = computed(() => props.error || internalError.value)
const cifTextResolved = computed(() => props.cifText || internalCifText.value)
const primary = computed(() => data.value?.primary_interface ?? null)

const methodText = computed(() => {
  if (!data.value || !primary.value) return ''
  return (
    data.value.method ||
    `${primary.value.label_a} ↔ ${primary.value.label_b} · PLIP 非共价相互作用 · pDockQ 8 Å 接触`
  )
})

const pdockqTier = computed(() => {
  const v = primary.value?.pdockq
  if (v == null) return 'low'
  if (v >= 0.49) return 'high'
  if (v >= 0.23) return 'mid'
  return 'low'
})

const pdockqHint = computed(() => {
  if (pdockqTier.value === 'high') return '界面质量较高（pDockQ ≥ 0.49）'
  if (pdockqTier.value === 'mid') return '界面质量中等（0.23 ≤ pDockQ < 0.49）'
  return '界面质量偏低（pDockQ < 0.23）'
})

const interactionChips = computed(() => {
  const p = primary.value
  if (!p) return []
  const ixSum = p.interaction_summary || {}
  return [
    { label: '氢键', value: ixSum.n_hbonds ?? 0, color: IX_LINE_CSS.hbond },
    { label: '盐桥', value: ixSum.n_salt_bridges ?? 0, color: IX_LINE_CSS.salt_bridge },
    { label: '疏水', value: ixSum.n_hydrophobic ?? 0, color: IX_LINE_CSS.hydrophobic },
    {
      label: 'π/水桥等',
      value: (ixSum.n_pi_stacking ?? 0) + (ixSum.n_water_bridges ?? 0) + (ixSum.n_polar_contacts ?? 0),
      color: IX_LINE_CSS.pi_stacking,
    },
    {
      label: '界面残基',
      value: (p.residues_a?.length || 0) + (p.residues_b?.length || 0),
      color: '#64748b',
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
    label: t === 'all' ? `全部 (${counts.all})` : `${IX_TYPE_LABELS[t]} (${counts[t]})`,
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

const chainBadgeA = computed(() => ({
  id: primary.value?.chain_a ?? 'A',
  label: primary.value?.label_a || primary.value?.chain_a || '链 A',
  role: 'target' as const,
}))

const chainBadgeB = computed(() => ({
  id: primary.value?.chain_b ?? 'B',
  label: primary.value?.label_b || primary.value?.chain_b || '链 B',
  role: 'binder' as const,
}))

async function fetchStructureText(): Promise<void> {
  if (props.cifText || !props.jobId) return
  try {
    const resp = await api.get<string>(`/api/jobs/${props.jobId}/structure`, {
      responseType: 'text',
      transformResponse: [(d) => d],
    })
    internalCifText.value = resp.data
  } catch {
    internalCifText.value = null
  }
}

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

function ixTypeClass(type: string): string {
  return `ix-type-pill ix-type-${type}`
}

watch(
  () => [props.jobId, props.interfaceData, props.cifText] as const,
  () => {
    ixFilter.value = 'all'
    activeRowIndex.value = null
    if (!props.cifText) internalCifText.value = null
    void Promise.all([fetchInterface(), fetchStructureText()])
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
  <section v-if="showSection" class="interface-section-card">
    <header class="interface-section-head">
      <div>
        <h2>结合界面分析</h2>
        <p v-if="methodText" class="interface-method">{{ methodText }}</p>
      </div>
      <div v-if="primary?.contact_pairs" class="interface-chain-badges">
        <span class="interface-chain-badge interface-chain-badge--target">
          <span class="interface-chain-badge__swatch" style="background: #5b8def" />
          {{ chainBadgeA.label }}
        </span>
        <span class="interface-chain-vs">↔</span>
        <span class="interface-chain-badge interface-chain-badge--binder">
          <span class="interface-chain-badge__swatch" style="background: #e07a5f" />
          {{ chainBadgeB.label }}
        </span>
      </div>
    </header>

    <div v-if="isLoading" v-loading="true" class="interface-loading">
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
      <div class="interface-hero-metrics">
        <div class="interface-pdockq-card" :class="`interface-pdockq-card--${pdockqTier}`">
          <div class="interface-pdockq-card__label">pDockQ</div>
          <div class="interface-pdockq-card__value">
            {{ primary?.pdockq?.toFixed(3) ?? '—' }}
          </div>
          <div class="interface-pdockq-card__hint">{{ pdockqHint }}</div>
        </div>

        <div class="interface-ix-chips">
          <div v-for="chip in interactionChips" :key="chip.label" class="interface-ix-chip">
            <span class="interface-ix-chip__dot" :style="{ background: chip.color }" />
            <span class="interface-ix-chip__val">{{ chip.value }}</span>
            <span class="interface-ix-chip__lbl">{{ chip.label }}</span>
          </div>
        </div>
      </div>

      <div class="interface-layout">
        <div class="interface-layout__viewer">
          <InterfaceViewer3d
            v-if="cifTextResolved"
            ref="viewerRef"
            :cif-text="cifTextResolved"
            :data="data!"
            :primary="primary"
          />
          <div v-else class="interface-loading">正在加载结构…</div>
        </div>

        <div class="interface-layout__side">
          <div class="interface-side-card">
            <div class="interface-side-card__head">
              PLIP 相互作用
              <span style="font-weight: 400; color: var(--muted); margin-left: 0.35rem">
                {{ primary?.interaction_summary?.n_total ?? primary?.interactions?.length ?? 0 }} 条
              </span>
            </div>
            <div class="interface-side-card__body">
              <div class="interaction-filters">
                <button
                  v-for="opt in filterOptions"
                  :key="opt.value"
                  type="button"
                  class="interaction-filter-pill"
                  :class="{ active: ixFilter === opt.value }"
                  @click="setFilter(opt.value)"
                >
                  {{ opt.label }}
                </button>
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
                  :row-class-name="({ rowIndex }) => (activeRowIndex === rowIndex ? 'ix-row-active' : '')"
                  @row-click="(row) => onRowClick(row, filteredInteractions.indexOf(row))"
                >
                  <el-table-column label="类型" width="88">
                    <template #default="{ row }">
                      <span :class="ixTypeClass(row.type)">
                        {{ interactionTypeLabel(row.type) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column label="链 A" min-width="96">
                    <template #default="{ row }">
                      {{ row.resname_a }} {{ row.chain_a }}{{ row.resnum_a }}
                    </template>
                  </el-table-column>
                  <el-table-column label="链 B" min-width="96">
                    <template #default="{ row }">
                      {{ row.resname_b }} {{ row.chain_b }}{{ row.resnum_b }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Å" width="56" align="right">
                    <template #default="{ row }">
                      {{ row.distance_angstrom.toFixed(1) }}
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>

          <div class="interface-side-card">
            <div class="interface-side-card__head">界面残基</div>
            <div class="interface-side-card__body">
              <div class="interface-residue-panel">
                <div class="interface-residue-col">
                  <h4>{{ chainBadgeA.label }} ({{ primary?.residues_a?.length ?? 0 }})</h4>
                  <ul class="interface-res-list">
                    <li v-for="r in primary?.residues_a ?? []" :key="`${r.chain_id}-${r.seq_num}`">
                      {{ r.resname }} {{ r.chain_id }}{{ r.seq_num }}
                    </li>
                  </ul>
                </div>
                <div class="interface-residue-col">
                  <h4>{{ chainBadgeB.label }} ({{ primary?.residues_b?.length ?? 0 }})</h4>
                  <ul class="interface-res-list">
                    <li v-for="r in primary?.residues_b ?? []" :key="`${r.chain_id}-${r.seq_num}`">
                      {{ r.resname }} {{ r.chain_id }}{{ r.seq_num }}
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <div v-if="data?.reference_tools?.length" class="interface-ref-tools">
            参考：
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
      </div>
    </div>
  </section>
</template>

<style lang="scss">
@use '@/styles/interface.scss';
</style>

<style scoped lang="scss">
.interface-panel__content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

:deep(.ix-row-active) {
  background: rgba(0, 172, 161, 0.08) !important;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
