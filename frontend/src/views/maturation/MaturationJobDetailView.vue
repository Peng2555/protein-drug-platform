<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMaturationJob,
  fetchMaturationJob,
  fetchMaturationVariants,
  maturationVariantsCsvUrl,
} from '@/api/maturation'
import type { MaturationJob, MaturationVariant } from '@/api/types'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { MATURATION_STAGE_LABELS, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const foldStore = useFoldTasksStore()

const loading = ref(true)
const job = ref<MaturationJob | null>(null)
const variants = ref<MaturationVariant[]>([])
const variantTotal = ref(0)
const minFrequency = ref(1)

const jobId = computed(() => route.params.id as string)

const results = computed(() => job.value?.results_json as Record<string, unknown> | null)

const metaLine = computed(() => {
  const j = job.value
  if (!j) return ''
  const p = j.params_json as Record<string, unknown> | null
  const src = p?.structure_source || '—'
  const cdr = Array.isArray(p?.cdr_mask) ? (p.cdr_mask as string[]).join(', ') : '—'
  const iggm = (p?.iggm || p) as Record<string, unknown>
  return [
    `结构来源: ${src}`,
    `CDR: ${cdr}`,
    iggm.num_samples != null ? `采样 ${iggm.num_samples}` : null,
    iggm.gpu_count != null ? `GPU×${iggm.gpu_count}` : null,
    j.created_at ? new Date(j.created_at).toLocaleString('zh-CN') : null,
  ]
    .filter(Boolean)
    .join(' · ')
})

async function loadDetail(silent = false) {
  if (!silent) loading.value = true
  try {
    job.value = await fetchMaturationJob(jobId.value)
    if (job.value.status === 'done') {
      const data = await fetchMaturationVariants(jobId.value, 200, 0, minFrequency.value)
      variants.value = data.items
      variantTotal.value = data.total
    } else {
      variants.value = []
      variantTotal.value = 0
    }
  } catch (e) {
    if (!silent) ElMessage.error(e instanceof Error ? e.message : '加载失败')
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
    await deleteMaturationJob(j.id)
    await foldStore.refreshMaturationTasks()
    router.push({ name: 'maturation' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function downloadCsv() {
  window.open(maturationVariantsCsvUrl(jobId.value), '_blank')
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

let pollHandle: ReturnType<typeof setInterval> | null = null

function setupPolling() {
  if (pollHandle) clearInterval(pollHandle)
  pollHandle = setInterval(async () => {
    if (!job.value || !['queued', 'running'].includes(job.value.status)) {
      if (pollHandle) clearInterval(pollHandle)
      pollHandle = null
      return
    }
    await loadDetail(true)
  }, 5000)
}

watch(jobId, () => {
  void loadDetail()
  setupPolling()
})

watch(minFrequency, () => {
  if (job.value?.status === 'done') void loadDetail(true)
})

onMounted(async () => {
  await loadDetail()
  setupPolling()
})

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle)
})
</script>

<template>
  <div v-loading="loading" class="maturation-detail page-card">
    <template v-if="job">
      <header class="detail-header">
        <div>
          <h2>{{ job.name || job.id.slice(0, 8) }}</h2>
          <p class="meta">{{ metaLine }}</p>
        </div>
        <div class="actions">
          <el-tag :type="statusTagType(job.status)" size="large">
            {{ statusLabel(job.status) }}
            <template v-if="job.stage && job.status === 'running'">
              · {{ MATURATION_STAGE_LABELS[job.stage] || job.stage }}
            </template>
          </el-tag>
          <el-button v-if="job.status === 'done'" size="small" @click="downloadCsv">
            下载 CSV
          </el-button>
          <el-button size="small" type="danger" plain @click="onDelete">删除</el-button>
        </div>
      </header>

      <section v-if="job.status === 'running' || job.status === 'queued'" class="stage-hint">
        任务运行中，页面将自动刷新。当前阶段：
        <strong>{{ MATURATION_STAGE_LABELS[job.stage || 'queued'] || job.stage }}</strong>
      </section>

      <section v-if="job.status === 'failed'" class="error-box">
        {{ job.error_message || '任务失败' }}
      </section>

      <section v-if="results" class="stats-grid">
        <div v-if="results.variant_count_raw != null" class="stat">
          <span class="label">原始样本</span>
          <span class="value">{{ results.variant_count_raw }}</span>
        </div>
        <div v-if="results.variant_count_dedup != null" class="stat">
          <span class="label">去重变异</span>
          <span class="value">{{ results.variant_count_dedup }}</span>
        </div>
        <div v-if="job.runtime_seconds != null" class="stat">
          <span class="label">耗时</span>
          <span class="value">{{ Math.round(job.runtime_seconds) }}s</span>
        </div>
      </section>

      <section v-if="job.status === 'done'" class="variants-section">
        <div class="variants-head">
          <h3>变异库 ({{ variantTotal }})</h3>
          <el-form-item label="最小频率" class="freq-filter">
            <el-input-number v-model="minFrequency" :min="0" :max="9999" size="small" />
          </el-form-item>
        </div>
        <el-table :data="variants" size="small" stripe max-height="480">
          <el-table-column prop="frequency" label="频率" width="80" sortable />
          <el-table-column prop="diff" label="差异" min-width="120" show-overflow-tooltip />
          <el-table-column prop="mutations" label="突变" min-width="120" show-overflow-tooltip />
          <el-table-column prop="antibody_seq_h" label="重链序列" min-width="280" show-overflow-tooltip />
        </el-table>
      </section>
    </template>
    <div v-else-if="!loading" class="empty-state">未找到任务</div>
  </div>
</template>

<style scoped lang="scss">
.maturation-detail {
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
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }
}

.stage-hint {
  padding: 0.75rem 1rem;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.error-box {
  padding: 0.75rem 1rem;
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.stats-grid {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1.25rem;

  .stat {
    display: flex;
    flex-direction: column;
    .label {
      font-size: 0.75rem;
      color: var(--el-text-color-secondary);
    }
    .value {
      font-size: 1.25rem;
      font-weight: 600;
    }
  }
}

.variants-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;

  h3 {
    margin: 0;
    font-size: 1rem;
  }

  .freq-filter {
    margin: 0;
  }
}
</style>
