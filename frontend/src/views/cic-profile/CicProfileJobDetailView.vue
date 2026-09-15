<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import HydroPatchViewer from '@/components/hydro/HydroPatchViewer.vue'
import {
  downloadCicProfileFile,
  fetchCicProfileCif,
  fetchCicProfileJob,
  fetchCicProfileProgress,
  fetchCicProfileRanked,
} from '@/api/cicProfile'
import type { CicProfileJob } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { CIC_PROFILE_STAGE_LABELS, statusLabel } from '@/utils/constants'
import { parseCicPatches, parseCicResidues, patchKindLabel, type CicPatchKind, type CicResidue } from '@/utils/cicPatches'
import type { HydroPatch } from '@/utils/hydroPatches'

const STAGE_ORDER = ['fold', 'patches', 'done']

const route = useRoute()
const router = useRouter()
const job = ref<CicProfileJob | null>(null)
const stage = ref('queued')
const patchRows = ref<Record<string, unknown>[]>([])
const residueRows = ref<Record<string, unknown>[]>([])
const summary = ref<Record<string, unknown> | null>(null)
const cifText = ref<string | null>(null)
const kindFilter = ref<'all' | CicPatchKind>('all')
const selectedPatchId = ref<string | null>(null)
const selectedResidue = ref<{ chainId: string; resi: number } | null>(null)

const params = computed(() => job.value?.params_json || {})
const residuesAll = computed(() => parseCicResidues(residueRows.value))
const patchesAll = computed(() => parseCicPatches(patchRows.value, residuesAll.value))
const patches = computed(() => {
  if (kindFilter.value === 'all') return patchesAll.value
  const prefix = kindFilter.value === 'positive' ? 'Pos' : kindFilter.value === 'negative' ? 'Neg' : 'Hyd'
  return patchesAll.value.filter((p) => p.patch_id.startsWith(prefix))
})
const residues = computed(() => {
  const selected = selectedPatchId.value
  if (selected) {
    return residuesAll.value.map((r) => {
      const inPatch =
        r.patch_id === selected || r.hydro_patch_id === selected || r.charge_patch_id === selected
      return { ...r, patch_id: inPatch ? selected : null }
    })
  }
  if (kindFilter.value === 'all') return residuesAll.value
  return residuesAll.value.map((r) => {
    const pid =
      kindFilter.value === 'hydrophobic'
        ? r.hydro_patch_id
        : kindFilter.value === 'positive' && r.charge_patch_id?.startsWith('Pos')
          ? r.charge_patch_id
          : kindFilter.value === 'negative' && r.charge_patch_id?.startsWith('Neg')
            ? r.charge_patch_id
            : null
    return { ...r, patch_id: pid }
  })
})

function stageLabel(s: string) {
  return CIC_PROFILE_STAGE_LABELS[s] || s
}
function stageIndex(s: string) {
  const i = STAGE_ORDER.indexOf(s)
  return i < 0 ? (s === 'queued' ? -1 : 0) : i
}
function selectPatch(id: string | null) {
  selectedPatchId.value = id
  selectedResidue.value = null
}
function pickResidue(chainId: string, resi: number) {
  selectedResidue.value = { chainId, resi }
  const hit = residuesAll.value.find((r) => r.chain === chainId && r.position === resi)
  selectedPatchId.value = hit?.patch_id ?? null
}
function residuePreview(labels: string[], n = 3) {
  if (labels.length <= n) return labels
  return [...labels.slice(0, n), `+${labels.length - n}`]
}
function fmt(v: unknown, digits = 3) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
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
function patchScoreMax() {
  return Math.max(...patches.value.map((p) => p.score), 0.001)
}
function patchKindOf(p: HydroPatch): CicPatchKind {
  if (p.patch_id.startsWith('Pos')) return 'positive'
  if (p.patch_id.startsWith('Neg')) return 'negative'
  return 'hydrophobic'
}
async function load() {
  const id = route.params.id as string
  try {
    job.value = await fetchCicProfileJob(id)
    const prog = await fetchCicProfileProgress(id)
    stage.value = prog.stage || job.value.stage || 'queued'
    if (job.value.status === 'done') {
      const data = await fetchCicProfileRanked(id)
      patchRows.value = data.patches
      residueRows.value = data.residues
      summary.value = data.summary
      cifText.value = await fetchCicProfileCif(id)
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
    patchRows.value = []
    residueRows.value = []
    summary.value = null
    cifText.value = null
    selectedPatchId.value = null
    selectedResidue.value = null
    await refresh()
  },
)
async function download(name: string) {
  if (!job.value) return
  try {
    await downloadCicProfileFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}
function onResidueRow(row: CicResidue) {
  pickResidue(row.chain, row.position)
}
</script>

<template>
  <div v-if="job" class="cic-page">
    <header class="cic-top">
      <div>
        <p class="kicker">抗体 CIC 表面斑</p>
        <h1>{{ job.name || job.id }}</h1>
        <p class="meta">
          {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · pH {{ params.ph ?? 7 }}
          · {{ params.structure_path ? '上传结构' : 'Boltz2 折抗体' }}
          · 耗时 {{ durationLabel(job.runtime_seconds) }}
        </p>
      </div>
      <div class="actions">
        <span class="status-pill" :data-status="job.status">{{ statusLabel(job.status) }}</span>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'cic-profile-new' })">新建任务</el-button>
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
      <div><span>实验 pH</span><strong>{{ params.ph ?? 7 }}</strong></div>
      <div><span>正电斑</span><strong>{{ summary?.n_positive_patches ?? '—' }}</strong></div>
      <div><span>负电斑</span><strong>{{ summary?.n_negative_patches ?? '—' }}</strong></div>
      <div><span>疏水斑</span><strong>{{ summary?.n_hydrophobic_patches ?? '—' }}</strong></div>
    </div>
    <template v-if="job.status === 'done'">
      <section class="stage">
        <div class="stage__view">
          <HydroPatchViewer
            :cif-text="cifText"
            :residues="residues"
            :patches="patches"
            :selected-patch-id="selectedPatchId"
            :selected-residue="selectedResidue"
            patch-color-label="表面斑"
            @select-patch="selectPatch"
            @residue-click="(p) => pickResidue(p.chainId, p.resi)"
          />
        </div>
        <aside class="rail">
          <div class="rail__head">
            <div>
              <h2>表面斑</h2>
              <p>红=正电，蓝=负电，橙=疏水。</p>
            </div>
            <button type="button" class="ghost" @click="selectPatch(null)">全部</button>
          </div>
          <div class="seg">
            <button type="button" :class="{ on: kindFilter === 'all' }" @click="kindFilter = 'all'">全部</button>
            <button type="button" :class="{ on: kindFilter === 'positive' }" @click="kindFilter = 'positive'">正电</button>
            <button type="button" :class="{ on: kindFilter === 'negative' }" @click="kindFilter = 'negative'">负电</button>
            <button type="button" :class="{ on: kindFilter === 'hydrophobic' }" @click="kindFilter = 'hydrophobic'">疏水</button>
          </div>
          <button
            v-for="p in patches"
            :key="p.patch_id"
            type="button"
            class="patch"
            :class="{ on: selectedPatchId === p.patch_id }"
            @click="selectPatch(selectedPatchId === p.patch_id ? null : p.patch_id)"
          >
            <span class="swatch" :style="{ background: p.color }" />
            <span class="patch__body">
              <span class="patch__row">
                <b>{{ p.patch_id }}</b>
                <em>{{ patchKindLabel(patchKindOf(p)) }} · {{ fmt(p.score) }}</em>
              </span>
              <span class="meter"><span class="fill" :style="{ width: `${(p.score / patchScoreMax()) * 100}%`, background: p.color }" /></span>
              <span class="chips">
                <span v-for="lab in residuePreview(p.residues)" :key="lab">{{ lab }}</span>
              </span>
            </span>
          </button>
          <el-empty v-if="!patches.length" description="未找到表面斑" />
        </aside>
      </section>
      <section class="results">
        <div class="results__bar">
          <p>斑残基</p>
          <div>
            <el-button size="small" type="primary" @click="download('patches.csv')">patches.csv</el-button>
            <el-button size="small" @click="download('residue_features.csv')">residue_features.csv</el-button>
            <el-button size="small" @click="download('pred.cif')">pred.cif</el-button>
          </div>
        </div>
        <el-table
          :data="residuesAll.filter((r) => r.patch_id && (!selectedPatchId || r.patch_id === selectedPatchId))"
          size="small"
          stripe
          max-height="380"
          highlight-current-row
          @row-click="onResidueRow"
        >
          <el-table-column label="斑" width="88">
            <template #default="{ row }">{{ row.patch_id }}</template>
          </el-table-column>
          <el-table-column label="类型" width="72">
            <template #default="{ row }">{{ patchKindLabel(row.patch_kind) }}</template>
          </el-table-column>
          <el-table-column label="残基" min-width="110">
            <template #default="{ row }">{{ row.chain }}:{{ row.aa }}{{ row.position }}</template>
          </el-table-column>
          <el-table-column prop="region" label="区域" width="80" />
          <el-table-column label="电荷" width="80">
            <template #default="{ row }">{{ fmt(row.charge) }}</template>
          </el-table-column>
          <el-table-column label="RSA" width="80">
            <template #default="{ row }">{{ fmt(row.rsa) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </template>
    <section v-else-if="job.status === 'running' || job.status === 'queued'" class="waiting">
      <h2>{{ stageLabel(stage) }}</h2>
      <p>完成后将显示正电 / 负电 / 疏水斑。每 5 秒刷新。</p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.cic-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1.5rem;
}
.cic-top {
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
.stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 0.9rem;
  @media (max-width: 1080px) {
    grid-template-columns: 1fr;
  }
}
.stage__view {
  height: 640px;
}
.rail {
  max-height: 640px;
  overflow: auto;
  padding: 0.9rem 0.85rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid var(--border);
}
.rail__head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.7rem;
  h2 {
    margin: 0;
    font-size: 0.92rem;
  }
  p {
    margin: 0.2rem 0 0;
    font-size: 0.74rem;
    color: var(--muted);
  }
}
.ghost {
  border: none;
  background: none;
  color: #1d4ed8;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}
.seg {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
  button {
    border: 1px solid var(--border);
    background: #f8fafc;
    border-radius: 999px;
    padding: 0.18rem 0.55rem;
    font-size: 0.72rem;
    cursor: pointer;
    &.on {
      background: #1d4ed8;
      color: #fff;
      border-color: #1d4ed8;
    }
  }
}
.patch {
  display: flex;
  width: 100%;
  text-align: left;
  margin-bottom: 0.5rem;
  padding: 0.55rem 0.6rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #f8fafc;
  cursor: pointer;
  gap: 0.6rem;
  &.on,
  &:hover {
    border-color: #93c5fd;
    background: #eff6ff;
  }
}
.swatch {
  width: 10px;
  border-radius: 999px;
  flex-shrink: 0;
}
.patch__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
}
.patch__row {
  display: flex;
  justify-content: space-between;
  font-size: 0.84rem;
  em {
    font-style: normal;
    font-size: 0.72rem;
    color: var(--muted);
  }
}
.meter {
  display: block;
  height: 3px;
  border-radius: 99px;
  background: #e2e8f0;
  .fill {
    display: block;
    height: 100%;
    border-radius: inherit;
  }
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  span {
    padding: 0.08rem 0.4rem;
    border-radius: 999px;
    background: #fff;
    border: 1px solid #e2e8f0;
    font-size: 0.68rem;
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
