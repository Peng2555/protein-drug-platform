<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadDesignFile, fetchDesignJob } from '@/api/design'
import type { DesignCandidate, DesignJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const job = ref<DesignJob | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const results = computed(() => job.value?.results_json as Record<string, unknown> | null)
const preview = computed((): DesignCandidate[] => {
  const raw = results.value?.candidates_preview
  return Array.isArray(raw) ? (raw as DesignCandidate[]) : []
})
const params = computed(() => job.value?.params_json || {})

async function load() {
  try {
    job.value = await fetchDesignJob(route.params.id as string)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}

function poll() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) {
    timer = setInterval(() => void load(), 4000)
  }
}

watch(() => job.value?.status, poll)
watch(() => route.params.id, async () => {
  await load()
})
onMounted(async () => {
  await load()
  poll()
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function download(name: string) {
  if (!job.value) return
  try {
    await downloadDesignFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

function goNew() {
  router.push({ name: 'design-new' })
}

function fmt(v: number | null | undefined, digits = 3) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div>
        <h2>{{ job.name || job.id }}</h2>
        <p>
          #{{ job.id.slice(0, 8) }} · {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · ProteinMPNN · {{ job.stage }}
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" @click="goNew">新建设计</el-button>
        <el-tag>{{ statusLabel(job.status) }}</el-tag>
      </div>
    </div>

    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <p>耗时：{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</p>

    <div class="meta-grid">
      <div><span>设计链</span>{{ params.designed_chains || '全部' }}</div>
      <div><span>序列数</span>{{ params.num_seq_per_target ?? '—' }}</div>
      <div><span>温度</span>{{ params.sampling_temp ?? '—' }}</div>
      <div><span>种子</span>{{ params.seed ?? '—' }}</div>
    </div>

    <template v-if="job.status === 'done' && results">
      <p class="stats">
        共 {{ results.n_candidates ?? preview.length }} 条设计序列
        <template v-if="results.top_score != null"> · 最优 score {{ fmt(Number(results.top_score)) }}</template>
        <template v-if="results.top_seq_recovery != null">
          · recovery {{ fmt(Number(results.top_seq_recovery), 3) }}
        </template>
      </p>
      <div class="file-actions">
        <el-button size="small" type="primary" @click="download('designed_sequences.fa')">下载 FASTA</el-button>
        <el-button size="small" @click="download('candidates.csv')">导出 CSV</el-button>
        <el-button size="small" @click="download('candidates.json')">导出 JSON</el-button>
        <el-button size="small" @click="download('summary.json')">下载摘要</el-button>
      </div>

      <h4>候选预览</h4>
      <el-table :data="preview" size="small" stripe empty-text="暂无候选">
        <el-table-column prop="sample" label="样本" width="70" />
        <el-table-column label="score" width="90">
          <template #default="{ row }">{{ fmt(row.score) }}</template>
        </el-table-column>
        <el-table-column label="recovery" width="90">
          <template #default="{ row }">{{ fmt(row.seq_recovery) }}</template>
        </el-table-column>
        <el-table-column prop="sequence" label="序列" min-width="240" show-overflow-tooltip />
      </el-table>
    </template>
  </div>
</template>

<style scoped lang="scss">
.detail-panel {
  max-width: 1100px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  h2 {
    margin: 0 0 0.25rem;
  }
  p {
    margin: 0;
    color: var(--muted);
    font-size: 0.85rem;
  }
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.6rem;
  margin: 0.75rem 0 1rem;
  font-size: 0.88rem;
  span {
    display: block;
    color: var(--muted);
    font-size: 0.72rem;
    margin-bottom: 0.15rem;
  }
}
.stats {
  margin: 0.5rem 0 0.75rem;
}
.file-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
h4 {
  margin: 0.5rem 0 0.6rem;
}
</style>
