<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadMaskingPeptideFile,
  fetchMaskingPeptideJob,
  fetchMaskingPeptideSequences,
} from '@/api/maskingPeptide'
import type { MaskingPeptideJob, MaskingPeptideSequenceRow } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const job = ref<MaskingPeptideJob | null>(null)
const sequences = ref<MaskingPeptideSequenceRow[]>([])
const summary = ref<Record<string, unknown> | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const params = computed(() => job.value?.params_json || {})
const entryMode = computed(() =>
  params.value.entry_mode === 'fold_job' ? 'Boltz2 抽链' : '上传抗体 PDB',
)

async function load() {
  const id = route.params.id as string
  try {
    job.value = await fetchMaskingPeptideJob(id)
    if (job.value.status === 'done' || job.value.results_json?.sequences) {
      const data = await fetchMaskingPeptideSequences(id)
      sequences.value = data.sequences
      summary.value = data.summary
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}

function poll() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) {
    timer = setInterval(() => void load(), 5000)
  }
}

watch(() => job.value?.status, poll)
watch(
  () => route.params.id,
  async () => {
    sequences.value = []
    summary.value = null
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
    await downloadMaskingPeptideFile(job.value.id, name)
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
          · {{ entryMode }} · {{ job.stage || '—' }}
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" @click="router.push({ name: 'masking-peptide-new' })">新建</el-button>
        <el-tag>{{ statusLabel(job.status) }}</el-tag>
      </div>
    </div>

    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />

    <p class="runtime">
      耗时：{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}
      <template v-if="job.status === 'running'">
        · 当前阶段：<strong>{{ job.stage }}</strong>
      </template>
    </p>

    <div v-if="params.hotspot_res" class="meta-grid">
      <div><span>Hotspot</span>{{ (params.hotspot_res as string[]).join(', ') }}</div>
      <div><span>骨架数</span>{{ params.total_designs ?? '—' }}</div>
      <div><span>MPNN 轮数</span>{{ params.mpnn_rounds ?? '—' }}</div>
      <div><span>肽段长度</span>{{ params.peptide_length ?? '—' }}</div>
      <div v-if="summary"><span>序列条数</span>{{ summary.n_sequences ?? sequences.length }}</div>
    </div>

    <template v-if="job.status === 'done' && sequences.length">
      <div class="file-actions">
        <el-button size="small" type="primary" @click="download('sequences_final.csv')">
          下载 sequences_final.csv
        </el-button>
        <el-button size="small" @click="download('structures.zip')">下载 structures.zip</el-button>
        <el-button size="small" @click="download('summary.json')">下载 summary.json</el-button>
      </div>

      <h4>设计序列（末轮 MPNN）</h4>
      <el-table :data="sequences.slice(0, 500)" size="small" stripe max-height="520">
        <el-table-column type="index" label="#" width="55" />
        <el-table-column prop="backbone" label="backbone" min-width="120" show-overflow-tooltip />
        <el-table-column prop="peptide_seq" label="peptide_seq" min-width="160" />
        <el-table-column label="mpnn_score" width="100">
          <template #default="{ row }">{{ fmt(row.mpnn_score) }}</template>
        </el-table-column>
        <el-table-column prop="length" label="length" width="72" />
      </el-table>
      <p v-if="sequences.length > 500" class="table-note">仅展示前 500 条，完整结果请下载 CSV。</p>
    </template>

    <el-empty
      v-else-if="job.status === 'done'"
      description="任务已完成但未找到 sequences_final.csv"
    />
    <el-empty v-else-if="job.status === 'running' || job.status === 'queued'" description="流水线运行中，请稍后刷新" />
  </div>
</template>

<style scoped lang="scss">
.detail-panel {
  padding: 1.5rem 1.75rem;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;

  h2 {
    margin: 0 0 0.35rem;
    font-size: 1.25rem;
  }

  p {
    margin: 0;
    font-size: 0.82rem;
    color: var(--muted);
  }
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.runtime {
  font-size: 0.85rem;
  color: var(--body);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.65rem;
  margin: 1rem 0;

  div {
    padding: 0.55rem 0.75rem;
    border-radius: var(--radius-sm);
    background: var(--bg-soft);
    border: 1px solid var(--border);
    font-size: 0.82rem;

    span {
      display: block;
      font-size: 0.68rem;
      color: var(--muted);
      margin-bottom: 0.15rem;
    }
  }
}

.file-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 1rem 0;
}

h4 {
  margin: 1rem 0 0.65rem;
  font-size: 0.95rem;
}

.table-note {
  margin: 0.5rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
</style>
