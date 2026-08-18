<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteSynthesisJob,
  fetchSynthesisCandidates,
  fetchSynthesisJob,
  synthesisCandidatesCsvUrl,
  synthesisOrderTxtUrl,
} from '@/api/synthesis'
import type { SynthesisCandidate, SynthesisJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const job = ref<SynthesisJob | null>(null)
const candidates = ref<SynthesisCandidate[]>([])
const total = ref(0)
const summary = ref<Record<string, unknown> | null>(null)
const viewKind = ref<'order' | 'matched'>('order')

const jobId = computed(() => route.params.id as string)

const statsLine = computed(() => {
  const s = summary.value
  if (!s) return ''
  return [
    s.parent_cdr3 ? `母本 CDR3 ${s.parent_cdr3}` : null,
    s.parent_v_gene ? `v_gene ${s.parent_v_gene}` : null,
    s.cdr3_region ? `区域 ${s.cdr3_region}` : null,
    s.shm_filtered != null ? `SHM筛选 ${s.shm_filtered}` : null,
    s.matched_count != null ? `匹配 ${s.matched_count}` : null,
    s.order_count != null ? `送合成 ${s.order_count}（A ${s.a_count} / B ${s.b_count}）` : null,
  ]
    .filter(Boolean)
    .join(' · ')
})

const inputFiles = computed(() => {
  const p = job.value?.params_json as Record<string, string> | null
  if (!p) return ''
  return [p.shm_file, p.iggm_file, p.origin_file].filter(Boolean).join(' · ')
})

async function loadDetail() {
  loading.value = true
  try {
    job.value = await fetchSynthesisJob(jobId.value)
    if (job.value.status === 'done') {
      const data = await fetchSynthesisCandidates(jobId.value, viewKind.value, 500, 0)
      candidates.value = data.items
      total.value = data.total
      summary.value = data.summary
    } else {
      candidates.value = []
      total.value = 0
      summary.value = null
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function onDelete() {
  const j = job.value
  if (!j) return
  try {
    await ElMessageBox.confirm(`确定删除「${j.name || j.id.slice(0, 8)}」吗？`, '删除', {
      type: 'warning',
    })
    await deleteSynthesisJob(j.id)
    router.push({ name: 'synthesis' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function downloadOrder() {
  window.open(synthesisCandidatesCsvUrl(jobId.value, 'order'), '_blank')
}

function downloadMatched() {
  window.open(synthesisCandidatesCsvUrl(jobId.value, 'matched'), '_blank')
}

function downloadTxt() {
  window.open(synthesisOrderTxtUrl(jobId.value), '_blank')
}

function priorityTagType(priority: string | null) {
  if (priority?.startsWith('A')) return 'success'
  if (priority?.startsWith('B')) return 'warning'
  return 'info'
}

watch(jobId, () => void loadDetail())
watch(viewKind, () => void loadDetail())
onMounted(() => void loadDetail())
</script>

<template>
  <div v-loading="loading" class="synthesis-detail page-card">
    <template v-if="job">
      <header class="detail-header">
        <div>
          <h2>{{ job.name || job.id.slice(0, 8) }}</h2>
          <p v-if="statsLine" class="meta">{{ statsLine }}</p>
          <p v-if="inputFiles" class="meta files">输入：{{ inputFiles }}</p>
        </div>
        <div class="actions">
          <el-tag :type="job.status === 'done' ? 'success' : 'danger'" size="large">
            {{ statusLabel(job.status) }}
          </el-tag>
          <el-button v-if="job.status === 'done'" size="small" @click="downloadOrder">
            下载送合成 CSV
          </el-button>
          <el-button v-if="job.status === 'done'" size="small" @click="downloadMatched">
            下载匹配明细
          </el-button>
          <el-button v-if="job.status === 'done'" size="small" @click="downloadTxt">
            下载 TXT 清单
          </el-button>
          <el-button size="small" type="danger" plain @click="onDelete">删除</el-button>
        </div>
      </header>

      <section v-if="job.status === 'failed'" class="error-box">
        {{ job.error_message || '筛选失败' }}
      </section>

      <section v-if="job.status === 'done'" class="results-section">
        <div class="results-head">
          <h3>
            {{ viewKind === 'order' ? '送合成清单' : '匹配明细' }} ({{ total }})
          </h3>
          <el-radio-group v-model="viewKind" size="small">
            <el-radio-button value="order">送合成清单</el-radio-button>
            <el-radio-button value="matched">匹配明细</el-radio-button>
          </el-radio-group>
        </div>

        <el-table v-if="viewKind === 'order'" :data="candidates" size="small" stripe max-height="520">
          <el-table-column prop="synthesis_id" label="ID" width="90" />
          <el-table-column prop="priority" label="档位" width="110">
            <template #default="{ row }">
              <el-tag :type="priorityTagType(row.priority)" size="small">
                {{ row.priority }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="iggm_variant_id" label="IgGM 变体" min-width="130" show-overflow-tooltip />
          <el-table-column prop="seq_count" label="count" width="80" sortable />
          <el-table-column prop="iggm_cdr3" label="CDR3" min-width="120" show-overflow-tooltip />
          <el-table-column
            prop="all_mutation_sites_for_synthesis"
            label="全部突变位点"
            min-width="150"
            show-overflow-tooltip
          />
          <el-table-column prop="extra_mutation_sites" label="额外SHM" min-width="110" show-overflow-tooltip />
          <el-table-column
            prop="synthesis_sequence"
            label="氨基酸序列"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
        </el-table>

        <el-table v-else :data="candidates" size="small" stripe max-height="520">
          <el-table-column prop="iggm_variant_id" label="IgGM 变体" min-width="120" show-overflow-tooltip />
          <el-table-column prop="seq_count" label="count" width="80" sortable />
          <el-table-column prop="iggm_cdr3" label="IgGM CDR3" min-width="120" show-overflow-tooltip />
          <el-table-column prop="has_extra_shm" label="额外SHM" width="90" />
          <el-table-column
            prop="cdr3_mutation_sites_in_shm_row"
            label="CDR3突变"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="extra_mutation_sites_in_shm_row"
            label="区外突变"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column prop="aa_sequence" label="氨基酸序列" min-width="180" show-overflow-tooltip />
        </el-table>
      </section>
    </template>
    <div v-else-if="!loading" class="empty-state">未找到记录</div>
  </div>
</template>

<style scoped lang="scss">
.synthesis-detail {
  padding: 1.25rem;
  min-height: 100%;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;

  h2 {
    margin: 0 0 0.35rem;
    font-size: 1.25rem;
  }

  .meta {
    margin: 0;
    font-size: 0.85rem;
    color: var(--el-text-color-secondary);

    &.files {
      margin-top: 0.25rem;
      font-size: 0.8rem;
    }
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}

.error-box {
  padding: 0.75rem 1rem;
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

.results-section {
  h3 {
    margin: 0;
    font-size: 1rem;
  }
}

.results-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  gap: 1rem;
}
</style>
