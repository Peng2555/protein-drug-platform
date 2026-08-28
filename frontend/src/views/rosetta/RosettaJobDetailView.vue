<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadRosettaEvalFile, fetchRosettaEvalJob } from '@/api/rosetta'
import type { RosettaEvalJob, RosettaEvalRow } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const job = ref<RosettaEvalJob | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const results = computed(() => job.value?.results_json as Record<string, unknown> | null)
const ranked = computed((): RosettaEvalRow[] => {
  const raw = results.value?.ranked
  return Array.isArray(raw) ? (raw as RosettaEvalRow[]) : []
})
const formatInfo = computed(() => (results.value?.format as Record<string, unknown> | undefined) || {})
const params = computed(() => job.value?.params_json || {})

async function load() {
  try {
    job.value = await fetchRosettaEvalJob(route.params.id as string)
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
watch(
  () => route.params.id,
  async () => {
    await load()
  },
)
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
    await downloadRosettaEvalFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

function fmt(v: number | string | null | undefined, digits = 3) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toFixed(digits)
}
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div>
        <h2>{{ job.name || job.id }}</h2>
        <p>
          #{{ job.id.slice(0, 8) }} · {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · Rosetta · {{ job.stage }}
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" @click="router.push({ name: 'rosetta-new' })">新建评价</el-button>
        <el-tag>{{ statusLabel(job.status) }}</el-tag>
      </div>
    </div>

    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <p>耗时：{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</p>

    <div class="meta-grid">
      <div><span>格式</span>{{ formatInfo.mode || '自动识别' }}</div>
      <div><span>界面</span>{{ formatInfo.interface || '—' }}</div>
      <div><span>nstruct</span>{{ params.nstruct ?? results?.nstruct ?? '—' }}</div>
      <div><span>n_jobs</span>{{ params.n_jobs ?? results?.n_jobs ?? '—' }}</div>
      <div><span>结构数</span>{{ results?.n_variants ?? (ranked.length || '—') }}</div>
    </div>

    <template v-if="job.status === 'done' && ranked.length">
      <p class="stats">
        WT：{{ results?.wt || '—' }}
        <template v-if="results?.top">
          · 排序第一 {{ (results.top as RosettaEvalRow).name }}
          （score {{ fmt((results.top as RosettaEvalRow).final_score) }}）
        </template>
      </p>
      <div class="file-actions">
        <el-button size="small" type="primary" @click="download('ranking.csv')">下载排序表</el-button>
        <el-button size="small" @click="download('scores.csv')">下载 scores.csv</el-button>
        <el-button size="small" @click="download('report.html')">下载 HTML 报告</el-button>
        <el-button size="small" @click="download('summary.json')">下载摘要</el-button>
      </div>
      <h4>突变体排序（final_score 越大越好；ΔΔG / ΔE 为负表示改善）</h4>
      <el-table :data="ranked" size="small" stripe>
        <el-table-column prop="rank" label="#" width="55" />
        <el-table-column prop="name" label="变体" min-width="120" />
        <el-table-column label="WT" width="60">
          <template #default="{ row }">{{ row.is_wt ? '是' : '' }}</template>
        </el-table-column>
        <el-table-column label="dG" width="90">
          <template #default="{ row }">{{ fmt(row.dG_separated) }}</template>
        </el-table-column>
        <el-table-column label="ΔΔG" width="90">
          <template #default="{ row }">{{ fmt(row.ddG) }}</template>
        </el-table-column>
        <el-table-column label="ΔE" width="90">
          <template #default="{ row }">{{ fmt(row.delta_E) }}</template>
        </el-table-column>
        <el-table-column label="dSASA" width="90">
          <template #default="{ row }">{{ fmt(row.dSASA_int, 1) }}</template>
        </el-table-column>
        <el-table-column label="HBond" width="80">
          <template #default="{ row }">{{ fmt(row.hbonds_int, 1) }}</template>
        </el-table-column>
        <el-table-column label="SC" width="80">
          <template #default="{ row }">{{ fmt(row.sc_value) }}</template>
        </el-table-column>
        <el-table-column label="综合分" width="90">
          <template #default="{ row }">{{ fmt(row.final_score) }}</template>
        </el-table-column>
        <el-table-column prop="flags" label="质控" min-width="140" show-overflow-tooltip />
      </el-table>
    </template>
  </div>
</template>

<style scoped lang="scss">
.detail-panel {
  max-width: 1200px;
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
