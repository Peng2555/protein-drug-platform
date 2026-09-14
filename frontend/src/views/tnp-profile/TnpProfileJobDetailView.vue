<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import HydroPatchViewer from '@/components/hydro/HydroPatchViewer.vue'
import {
  downloadTnpProfileFile,
  fetchTnpProfileCif,
  fetchTnpProfileJob,
  fetchTnpProfileProgress,
  fetchTnpProfileRanked,
} from '@/api/tnpProfile'
import type { TnpProfileJob } from '@/api/types'
import { TNP_PROFILE_STAGE_LABELS, statusLabel } from '@/utils/constants'
import { parseHydroPatches, parseHydroResidues } from '@/utils/hydroPatches'

const STAGE_ORDER = ['fold', 'score', 'done']
const METRIC_LABELS: Record<string, string> = {
  L: 'Total CDR Length',
  L3: 'CDR3 Length',
  C: 'CDR3 Compactness',
  PSH: 'Patches of Surface Hydrophobicity',
  PPC: 'Patches of Positive Charge',
  PNC: 'Patches of Negative Charge',
}

const route = useRoute()
const router = useRouter()
const job = ref<TnpProfileJob | null>(null)
const stage = ref('queued')
const patchRows = ref<Record<string, unknown>[]>([])
const residueRows = ref<Record<string, unknown>[]>([])
const summary = ref<Record<string, unknown> | null>(null)
const cifText = ref<string | null>(null)
const selectedPatchId = ref<string | null>(null)
const selectedResidue = ref<{ chainId: string; resi: number } | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const params = computed(() => job.value?.params_json || {})
const residuesAll = computed(() => parseHydroResidues(residueRows.value))
const patches = computed(() => parseHydroPatches(patchRows.value, residuesAll.value))
const residues = computed(() => {
  if (!selectedPatchId.value) return residuesAll.value
  return residuesAll.value.map((r) => ({
    ...r,
    patch_id: r.patch_id === selectedPatchId.value ? r.patch_id : null,
  }))
})
const metrics = computed(() => {
  const list = (summary.value?.metrics as Record<string, unknown>[] | undefined) || []
  return list
})

function stageLabel(s: string) {
  return TNP_PROFILE_STAGE_LABELS[s] || s
}
function stageIndex(s: string) {
  const i = STAGE_ORDER.indexOf(s)
  return i < 0 ? (s === 'queued' ? -1 : 0) : i
}
function flagLabel(flag: unknown) {
  if (flag === 'green') return '绿'
  if (flag === 'amber') return '黄'
  if (flag === 'red') return '红'
  return '待标定'
}
function threshHint(m: Record<string, unknown>) {
  const t = m.thresholds as Record<string, unknown> | undefined
  if (!t) return ''
  const p05 = t.p05
  const p95 = t.p95
  const lo = t.red_lt
  const hi = t.red_gt
  if (m.id === 'PPC' || m.id === 'PNC') {
    return `黄 ≥ ${p95} · 红 > ${hi}`
  }
  return `黄 ≤${p05} 或 ≥${p95} · 红 <${lo} 或 >${hi}`
}
function fmt(v: unknown, digits = 3) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  if (Number.isInteger(n) && Math.abs(n) >= 1) return String(n)
  return n.toFixed(digits)
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
    job.value = await fetchTnpProfileJob(id)
    const prog = await fetchTnpProfileProgress(id)
    stage.value = prog.stage || job.value.stage || 'queued'
    if (job.value.status === 'done') {
      const data = await fetchTnpProfileRanked(id)
      patchRows.value = data.patches
      residueRows.value = data.residues
      summary.value = data.summary
      cifText.value = await fetchTnpProfileCif(id)
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
    patchRows.value = []
    residueRows.value = []
    summary.value = null
    cifText.value = null
    selectedPatchId.value = null
    selectedResidue.value = null
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
    await downloadTnpProfileFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}
</script>

<template>
  <div v-if="job" class="tnp-page">
    <header class="tnp-top">
      <div>
        <p class="kicker">VHH 可开发性画像 · Boltz2 · Kabat</p>
        <h1>{{ job.name || job.id }}</h1>
        <p class="meta">
          {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · {{ params.structure_path ? '上传结构' : 'Boltz2 折抗体' }}
          · 耗时 {{ durationLabel(job.runtime_seconds) }}
        </p>
      </div>
      <div class="actions">
        <span class="status-pill" :data-status="job.status">{{ statusLabel(job.status) }}</span>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'tnp-profile-new' })">新建任务</el-button>
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
      <div><span>Tetrad</span><strong>{{ summary?.tetrad_motif ?? '—' }}</strong></div>
      <div><span>L</span><strong>{{ summary?.L ?? '—' }}</strong></div>
      <div><span>L3</span><strong>{{ summary?.L3 ?? '—' }}</strong></div>
      <div><span>C</span><strong>{{ fmt(summary?.C) }}</strong></div>
    </div>
    <template v-if="job.status === 'done'">
      <section class="lights">
        <button
          v-for="m in metrics"
          :key="String(m.id)"
          type="button"
          class="light"
          :data-flag="String(m.flag || 'pending')"
        >
          <span class="dot" />
          <span class="light__id">{{ m.id }}</span>
          <strong>{{ fmt(m.value) }}</strong>
          <em>{{ flagLabel(m.flag) }}</em>
          <small>{{ METRIC_LABELS[String(m.id)] || m.id }}</small>
          <small class="hint">{{ threshHint(m) }}</small>
        </button>
      </section>
      <section class="stage">
        <div class="stage__view">
          <HydroPatchViewer
            :cif-text="cifText"
            :residues="residues"
            :patches="patches"
            :selected-patch-id="selectedPatchId"
            :selected-residue="selectedResidue"
            patch-color-label="CDR 附近"
            @select-patch="selectedPatchId = $event"
            @residue-click="(p) => (selectedResidue = { chainId: p.chainId, resi: p.resi })"
          />
        </div>
        <aside class="rail">
          <h2>CDR vicinity</h2>
          <p>Kabat CDR±2 及 4 Å 邻域表面残基，用于 PSH / PPC / PNC。</p>
          <p class="mono">H1 {{ summary?.cdr_h1 }}</p>
          <p class="mono">H2 {{ summary?.cdr_h2 }}</p>
          <p class="mono">H3 {{ summary?.cdr_h3 }}</p>
          <el-button size="small" type="primary" @click="download('summary.json')">summary.json</el-button>
          <el-button size="small" @click="download('residue_features.csv')">residue_features.csv</el-button>
          <el-button size="small" @click="download('pred.cif')">pred.cif</el-button>
        </aside>
      </section>
    </template>
    <section v-else-if="job.status === 'running' || job.status === 'queued'" class="waiting">
      <h2>{{ stageLabel(stage) }}</h2>
      <p>完成后显示六项交通灯。每 5 秒刷新。</p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.tnp-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1.5rem;
}
.tnp-top {
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
  letter-spacing: 0.06em;
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
.lights {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  @media (max-width: 900px) {
    grid-template-columns: 1fr 1fr;
  }
}
.light {
  display: grid;
  grid-template-columns: 10px 1fr;
  grid-template-rows: auto auto auto;
  column-gap: 0.55rem;
  text-align: left;
  padding: 0.75rem 0.85rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fff;
  .dot {
    grid-row: 1 / span 3;
    width: 10px;
    border-radius: 999px;
    background: #cbd5e1;
  }
  &__id {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--muted);
  }
  strong {
    font-size: 1.15rem;
  }
  em {
    font-style: normal;
    font-size: 0.72rem;
  }
  small {
    grid-column: 2;
    color: var(--muted);
    font-size: 0.72rem;
  }
  .hint {
    font-size: 0.68rem;
  }
  &[data-flag='green'] .dot {
    background: #16a34a;
  }
  &[data-flag='amber'] .dot {
    background: #d97706;
  }
  &[data-flag='red'] .dot {
    background: #dc2626;
  }
}
.stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 0.9rem;
  @media (max-width: 1080px) {
    grid-template-columns: 1fr;
  }
}
.stage__view {
  height: 640px;
}
.rail {
  padding: 0.9rem 0.85rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid var(--border);
  h2 {
    margin: 0 0 0.4rem;
    font-size: 0.92rem;
  }
  p {
    margin: 0 0 0.55rem;
    font-size: 0.78rem;
    color: var(--muted);
  }
  .mono {
    font-family: ui-monospace, monospace;
    font-size: 0.72rem;
    word-break: break-all;
    color: var(--body);
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
