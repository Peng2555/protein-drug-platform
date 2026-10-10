<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadTmDisulfideFile,
  fetchTmDisulfideJob,
  fetchTmDisulfideProgress,
  fetchTmDisulfideRanked,
} from '@/api/tmDisulfide'
import type { TmDisulfideJob } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { TM_DISULFIDE_STAGE_LABELS, statusLabel } from '@/utils/constants'

const STAGE_ORDER = ['qc', 'ensemble', 'sites', 'pairs', 'geometry', 'build', 'energy', 'done']

const route = useRoute()
const router = useRouter()
const job = ref<TmDisulfideJob | null>(null)
const stage = ref('queued')
const candidates = ref<Record<string, unknown>[]>([])
const summary = ref<Record<string, unknown> | null>(null)

const params = computed(() => job.value?.params_json || {})

function stageLabel(s: string) {
  return TM_DISULFIDE_STAGE_LABELS[s] || s
}
function stageIndex(s: string) {
  const i = STAGE_ORDER.indexOf(s)
  return i < 0 ? (s === 'queued' ? -1 : 0) : i
}
function fmt(v: unknown, digits = 2) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toFixed(digits)
}
function yesNo(v: unknown) {
  const text = String(v ?? '').toLowerCase()
  return text === 'true' || text === '1' || v === true ? '是' : '否'
}
function durationLabel(sec: number | null | undefined) {
  if (!sec) return '—'
  const s = Math.round(sec)
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  return r ? `${m} 分 ${r} 秒` : `${m} 分钟`
}
async function load() {
  const id = route.params.id as string
  try {
    job.value = await fetchTmDisulfideJob(id)
    const prog = await fetchTmDisulfideProgress(id)
    stage.value = prog.stage || job.value.stage || 'queued'
    if (job.value.status === 'done') {
      const data = await fetchTmDisulfideRanked(id)
      candidates.value = data.candidates
      summary.value = data.summary
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}
const pollingEnabled = computed(() =>
  Boolean(job.value && ['queued', 'running'].includes(job.value.status)),
)
const { refresh } = usePolling(load, pollingEnabled)

watch(
  () => route.params.id,
  async () => {
    candidates.value = []
    summary.value = null
    await refresh()
  },
)
async function download(name: string) {
  if (!job.value) return
  try {
    await downloadTmDisulfideFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}
</script>

<template>
  <div v-if="job" class="tm-page">
    <header class="tm-top">
      <div>
        <p class="kicker">抗体额外二硫键</p>
        <h1>{{ job.name || job.id }}</h1>
        <p class="meta">
          {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · 源作业 {{ params.source_job_id || job.parent_job_id || '—' }}
          · {{ params.n_models ?? '—' }} 套模型
          · 耗时 {{ durationLabel(job.runtime_seconds) }}
        </p>
      </div>
      <div class="actions">
        <span class="status-pill" :data-status="job.status">{{ statusLabel(job.status) }}</span>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'tm-disulfide-new' })">新建任务</el-button>
      </div>
    </header>
    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <ol class="stepper">
      <li
        v-for="(s, i) in STAGE_ORDER"
        :key="s"
        :class="{ done: stageIndex(stage) > i || job.status === 'done', current: stage === s && job.status !== 'done' }"
      >
        <span class="idx">{{ i + 1 }}</span>
        {{ stageLabel(s) }}
      </li>
    </ol>
    <div class="kpi">
      <div><span>几何通过</span><strong>{{ summary?.n_geometry_pass ?? '—' }}</strong></div>
      <div><span>成键通过</span><strong>{{ summary?.n_build_pass ?? '—' }}</strong></div>
      <div><span>能量通过</span><strong>{{ summary?.n_energy_pass ?? '—' }}</strong></div>
      <div><span>模型套数</span><strong>{{ summary?.n_models ?? params.n_models ?? '—' }}</strong></div>
    </div>
    <template v-if="job.status === 'done'">
      <section class="results">
        <div class="results__bar">
          <p>候选（能量通过优先，再按 median ΔΔG）</p>
          <div>
            <el-button size="small" type="primary" @click="download('candidates.csv')">candidates.csv</el-button>
            <el-button size="small" @click="download('summary.json')">summary.json</el-button>
          </div>
        </div>
        <el-table :data="candidates" size="small" stripe max-height="520">
          <el-table-column prop="rank" label="#" width="56" />
          <el-table-column prop="pair_id" label="pair" min-width="140" />
          <el-table-column prop="site1" label="位点 1" width="88" />
          <el-table-column prop="site2" label="位点 2" width="88" />
          <el-table-column label="几何" width="72">
            <template #default="{ row }">{{ yesNo(row.geometry_pass) }}</template>
          </el-table-column>
          <el-table-column label="成键" width="72">
            <template #default="{ row }">{{ yesNo(row.build_pass) }}</template>
          </el-table-column>
          <el-table-column label="能量" width="72">
            <template #default="{ row }">{{ yesNo(row.energy_pass) }}</template>
          </el-table-column>
          <el-table-column label="median ΔΔG" width="120">
            <template #default="{ row }">{{ fmt(row.median_ddg) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!candidates.length" description="没有候选" />
      </section>
    </template>
    <section v-else-if="job.status === 'running' || job.status === 'queued'" class="waiting">
      <h2>{{ stageLabel(stage) }}</h2>
      <p>CPU 队列运行 PyRosetta。完成后按 ΔΔG 列出通过对。每 5 秒刷新。</p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.tm-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1.5rem;
}
.tm-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  h1 {
    margin: 0.15rem 0 0.3rem;
    font-size: 1.45rem;
    font-weight: 800;
  }
}
.kicker {
  margin: 0;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #1d4ed8;
}
.meta {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.status-pill {
  padding: 0.2rem 0.65rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  background: #ecfdf5;
  color: #0f766e;
  &[data-status='failed'] {
    background: #fef2f2;
    color: #b91c1c;
  }
  &[data-status='running'],
  &[data-status='queued'] {
    background: #eff6ff;
    color: #1d4ed8;
  }
}
.stepper {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin: 0;
  padding: 0;
  list-style: none;
  li {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.28rem 0.7rem 0.28rem 0.35rem;
    border-radius: 999px;
    font-size: 0.78rem;
    color: var(--muted);
    background: #fff;
    border: 1px solid var(--border);
  }
  .idx {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 0.68rem;
    font-weight: 700;
    background: #e2e8f0;
  }
  .done {
    border-color: #93c5fd;
    background: #eff6ff;
    color: #1d4ed8;
    .idx {
      background: #1d4ed8;
      color: #fff;
    }
  }
  .current {
    border-color: #93c5fd;
    background: #eff6ff;
    font-weight: 600;
  }
}
.kpi {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.65rem;
  @media (max-width: 900px) {
    grid-template-columns: repeat(2, 1fr);
  }
  div {
    padding: 0.7rem 0.85rem;
    border-radius: 14px;
    background: #fff;
    border: 1px solid var(--border);
  }
  span {
    display: block;
    font-size: 0.7rem;
    color: var(--muted);
  }
}
.results {
  padding: 1rem 1.1rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid var(--border);
}
.results__bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  p {
    margin: 0;
    font-weight: 600;
  }
}
.waiting {
  padding: 1.5rem;
  border-radius: 16px;
  border: 1px dashed #93c5fd;
  background: #eff6ff;
  h2 {
    margin: 0 0 0.3rem;
  }
  p {
    margin: 0;
    color: var(--muted);
  }
}
</style>
