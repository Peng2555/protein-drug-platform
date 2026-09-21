<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import HydroPatchViewer from '@/components/hydro/HydroPatchViewer.vue'
import {
  downloadHydroRedesignFile,
  fetchHydroRedesignCif,
  fetchHydroRedesignJob,
  fetchHydroRedesignProgress,
  fetchHydroRedesignRanked,
} from '@/api/hydroRedesign'
import type { HydroRedesignJob } from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { HYDRO_REDESIGN_STAGE_LABELS, statusLabel } from '@/utils/constants'
import { parseHydroPatches, parseHydroResidues, type HydroPatch, type HydroResidue } from '@/utils/hydroPatches'

const STAGE_ORDER = ['fold', 'patches', 'enumerate', 'done']

const route = useRoute()
const router = useRouter()
const job = ref<HydroRedesignJob | null>(null)
const stage = ref('queued')
const mutations = ref<Record<string, unknown>[]>([])
const wetlab = ref<Record<string, unknown>[]>([])
const patchRows = ref<Record<string, unknown>[]>([])
const residueRows = ref<Record<string, unknown>[]>([])
const summary = ref<Record<string, unknown> | null>(null)
const cifText = ref<string | null>(null)
const tableTab = ref<'wetlab' | 'all' | 'patches'>('patches')
const selectedPatchId = ref<string | null>(null)
const selectedResidue = ref<{ chainId: string; resi: number } | null>(null)

const params = computed(() => job.value?.params_json || {})
const residues = computed(() => parseHydroResidues(residueRows.value))
const mutableSiteKeys = computed(() => {
  const keys = new Set<string>()
  for (const m of mutations.value) {
    const chain = String(m.chain || '')
    const pos = Number(m.position)
    if (chain && Number.isFinite(pos) && pos > 0) keys.add(`${chain}:${pos}`)
  }
  return keys
})
const chainLen = computed(() => {
  const map = new Map<string, number>()
  for (const r of residues.value) {
    map.set(r.chain, Math.max(map.get(r.chain) || 0, r.position))
  }
  return map
})
function residueMutLabel(r: { chain: string; position: number; aa: string; region: string }) {
  if (mutableSiteKeys.value.has(`${r.chain}:${r.position}`)) return '可突变'
  if (String(r.aa ?? '') === 'C') return '冻结·Cys'
  if (String(r.region ?? '').startsWith('CDR') && !params.value.allow_cdr) return '冻结·CDR'
  const nlen = chainLen.value.get(String(r.chain)) || 0
  const pos = Number(r.position)
  if (pos <= 4 || (nlen > 0 && pos > nlen - 4)) return '冻结·端区'
  return '未枚举'
}
const residuesWithMut = computed(() =>
  residues.value.map((r) => ({ ...r, mutLabel: residueMutLabel(r) })),
)
const patches = computed(() => parseHydroPatches(patchRows.value, residues.value))
const selectedPatch = computed(
  () => patches.value.find((p) => p.patch_id === selectedPatchId.value) ?? null,
)
const selectedPatchMutations = computed(() => {
  const pid = selectedPatchId.value
  if (!pid) return []
  return mutations.value.filter((m) => String(m.patch_id || '') === pid)
})

function stageLabel(s: string) {
  return HYDRO_REDESIGN_STAGE_LABELS[s] || s
}

function stageIndex(s: string) {
  const i = STAGE_ORDER.indexOf(s)
  return i < 0 ? (s === 'queued' ? -1 : 0) : i
}

function selectPatch(id: string | null) {
  selectedPatchId.value = id
  selectedResidue.value = null
}

function pickResidue(chainId: string, resi: number, patchId?: string | null) {
  selectedResidue.value = { chainId, resi }
  if (patchId !== undefined) {
    selectedPatchId.value = patchId
    return
  }
  const hit = residues.value.find((r) => r.chain === chainId && r.position === resi)
  selectedPatchId.value = hit?.patch_id ?? null
}

async function load() {
  const id = route.params.id as string
  try {
    job.value = await fetchHydroRedesignJob(id)
    const prog = await fetchHydroRedesignProgress(id)
    stage.value = prog.stage || job.value.stage || 'queued'
    if (job.value.status === 'done') {
      const data = await fetchHydroRedesignRanked(id)
      mutations.value = data.mutations
      wetlab.value = data.wetlab
      patchRows.value = data.patches
      residueRows.value = data.residues
      summary.value = data.summary
      cifText.value = await fetchHydroRedesignCif(id)
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
    mutations.value = []
    wetlab.value = []
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
    await downloadHydroRedesignFile(job.value.id, name)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
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

function residuePreview(labels: string[], n = 3) {
  if (labels.length <= n) return labels
  return [...labels.slice(0, n), `+${labels.length - n}`]
}

function onResidueRow(row: HydroResidue) {
  pickResidue(row.chain, row.position, row.patch_id)
}

function onMutationRow(row: Record<string, unknown>) {
  const chain = String(row.chain || '')
  const pos = Number(row.position)
  const pid = String(row.patch_id || '') || null
  if (chain && Number.isFinite(pos) && pos > 0) {
    pickResidue(chain, pos, pid)
    return
  }
  selectPatch(pid)
}

function patchScoreMax() {
  const m = Math.max(...patches.value.map((p) => p.score), 0.001)
  return m
}

const nMutableSites = computed(() => {
  const raw = summary.value?.n_mutable_sites
  if (raw != null && raw !== '') {
    const n = Number(raw)
    if (Number.isFinite(n)) return n
  }
  return mutableSiteKeys.value.size
})

const tableRows = computed(() => {
  if (tableTab.value === 'wetlab') return wetlab.value
  if (tableTab.value === 'patches') return []
  return mutations.value
})

function isPatchActive(p: HydroPatch) {
  return selectedPatchId.value === p.patch_id
}

function patchHasMutable(p: HydroPatch) {
  return residues.value.some(
    (r) => r.patch_id === p.patch_id && residueMutLabel(r) === '可突变',
  )
}

const mutationTable = computed(() => {
  if (tableTab.value === 'all' && selectedPatchId.value) return selectedPatchMutations.value
  return tableRows.value
})
</script>

<template>
  <div v-if="job" class="hydro-page">
    <header class="hydro-top">
      <div>
        <p class="hydro-top__kicker">抗体疏水性改造</p>
        <h1>{{ job.name || job.id }}</h1>
        <p class="hydro-top__meta">
          {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · {{ params.structure_path ? '上传结构' : 'Boltz2 折抗体' }}
          · 耗时 {{ durationLabel(job.runtime_seconds) }}
        </p>
      </div>
      <div class="hydro-top__actions">
        <span class="status-pill" :data-status="job.status">{{ statusLabel(job.status) }}</span>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" type="primary" plain @click="router.push({ name: 'hydro-redesign-new' })">
          新建任务
        </el-button>
      </div>
    </header>

    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />

    <ol class="stepper">
      <li
        v-for="(s, i) in STAGE_ORDER"
        :key="s"
        :class="{
          done: stageIndex(stage) > i || job.status === 'done',
          current: stage === s && job.status !== 'done',
        }"
      >
        <span class="stepper__idx">{{ i + 1 }}</span>
        {{ stageLabel(s) }}
      </li>
    </ol>

    <div class="kpi">
      <div>
        <span>CDR</span>
        <strong>{{ params.allow_cdr ? '可突变' : '冻结' }}</strong>
      </div>
      <div>
        <span>亲水字母表</span>
        <strong>{{ params.allow_charged ? 'STNQA + DEKR' : 'STNQA' }}</strong>
      </div>
      <div>
        <span>疏水尺度</span>
        <strong>{{ summary?.hydrophobicity_scale ?? 'SAP' }}</strong>
      </div>
      <div>
        <span>疏水斑</span>
        <strong>{{ summary?.n_patches ?? patches.length }}</strong>
      </div>
      <div>
        <span>高 SAP 残基</span>
        <strong>{{ summary?.n_high_sap ?? summary?.n_surface_hydro ?? '—' }}</strong>
      </div>
      <div>
        <span>可突变位点</span>
        <strong>{{ nMutableSites }}</strong>
      </div>
      <div>
        <span>突变条数</span>
        <strong>{{ summary?.n_mutations ?? mutations.length }}</strong>
      </div>
      <div>
        <span>湿实验短名单</span>
        <strong>{{ summary?.n_wetlab ?? wetlab.length }}</strong>
      </div>
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
            @select-patch="selectPatch"
            @residue-click="(p) => pickResidue(p.chainId, p.resi)"
          />
        </div>
        <aside class="rail">
          <div class="rail__head">
            <div>
              <h2>可改造疏水斑</h2>
              <p>表面 + 自身疏水 + SAP≥0.5；点残基只描这一处，点斑才描整块。</p>
            </div>
            <button type="button" class="ghost" @click="selectPatch(null)">全部</button>
          </div>
          <button
            v-for="p in patches"
            :key="p.patch_id"
            type="button"
            class="patch"
            :class="{ on: isPatchActive(p) }"
            @click="selectPatch(isPatchActive(p) ? null : p.patch_id)"
          >
            <span class="patch__swatch" :style="{ background: p.color }" />
            <span class="patch__body">
              <span class="patch__row">
                <b>{{ p.patch_id }}</b>
                <em>{{ fmt(p.score) }}</em>
              </span>
              <span class="patch__meter">
                <span class="patch__fill" :style="{ width: `${(p.score / patchScoreMax()) * 100}%`, background: p.color }" />
              </span>
              <span class="patch__chips">
                <span v-for="lab in residuePreview(p.residues)" :key="lab">{{ lab }}</span>
                <span v-if="!patchHasMutable(p)" class="patch__frozen">CDR 冻结</span>
              </span>
            </span>
          </button>
          <el-empty v-if="!patches.length" description="未找到表面疏水斑" />
        </aside>
      </section>

      <section class="results">
        <div class="results__bar">
          <div class="seg">
            <button type="button" :class="{ on: tableTab === 'patches' }" @click="tableTab = 'patches'">
              斑残基
            </button>
            <button type="button" :class="{ on: tableTab === 'wetlab' }" @click="tableTab = 'wetlab'">
              湿实验
            </button>
            <button type="button" :class="{ on: tableTab === 'all' }" @click="tableTab = 'all'">全部突变</button>
          </div>
          <div class="downloads">
            <el-button
              size="small"
              type="primary"
              :disabled="!mutations.length"
              @click="download('all_mutant_sequences.fasta')"
            >
              下载全部序列
            </el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!(wetlab.length || mutations.length)"
              @click="download('top20_mutant_sequences.fasta')"
            >
              下载推荐前20
            </el-button>
            <el-button size="small" @click="download('wetlab.csv')">wetlab.csv</el-button>
            <el-button size="small" @click="download('mutations.csv')">mutations.csv</el-button>
            <el-button size="small" @click="download('patches.csv')">patches.csv</el-button>
            <el-button size="small" @click="download('pred.cif')">pred.cif</el-button>
          </div>
        </div>

        <p v-if="selectedPatch" class="focus">
          当前聚焦
          <b :style="{ color: selectedPatch.color }">{{ selectedPatch.patch_id }}</b>
          · {{ selectedPatch.residues.length }} 残基
          · {{ selectedPatchMutations.length }} 条突变
          <button type="button" class="ghost" @click="tableTab = 'all'">查看这些突变</button>
        </p>

        <el-table
          v-if="tableTab === 'patches'"
          :data="residuesWithMut.filter((r) => r.patch_id && (!selectedPatchId || r.patch_id === selectedPatchId))"
          size="small"
          stripe
          max-height="380"
          highlight-current-row
          @row-click="onResidueRow"
        >
          <el-table-column label="斑" width="88">
            <template #default="{ row }">
              <span class="dot" :style="{ background: patches.find((p) => p.patch_id === row.patch_id)?.color }" />
              {{ row.patch_id }}
            </template>
          </el-table-column>
          <el-table-column label="残基" min-width="110">
            <template #default="{ row }">{{ row.chain }}:{{ row.aa }}{{ row.position }}</template>
          </el-table-column>
          <el-table-column prop="region" label="区域" width="80" />
          <el-table-column label="RSA" width="88">
            <template #default="{ row }">{{ fmt(row.rsa) }}</template>
          </el-table-column>
          <el-table-column label="SAP" width="88">
            <template #default="{ row }">{{ fmt(row.sap ?? row.hydro_sasa) }}</template>
          </el-table-column>
          <el-table-column label="σ" width="72">
            <template #default="{ row }">{{ fmt(row.sap_std) }}</template>
          </el-table-column>
          <el-table-column label="突变" width="100">
            <template #default="{ row }">
              <span class="mut-flag" :data-ok="row.mutLabel === '可突变'">
                {{ row.mutLabel }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="tableTab === 'patches'" class="hint">
          「可突变」只计写入 mutations.csv 的位点。
          可改造斑：表面暴露、自身疏水、SAP ≥ 0.5，侧链 6 Å 聚类。CDR 默认冻结。
          CDR、N/C 端 4 位、Cys 标为冻结。
        </p>

        <el-table
          v-else
          :data="mutationTable.slice(0, 200)"
          size="small"
          stripe
          max-height="420"
          highlight-current-row
          @row-click="onMutationRow"
        >
          <el-table-column prop="rank" label="#" width="55" />
          <el-table-column prop="label" label="突变" min-width="130" />
          <el-table-column prop="region" label="区域" width="80" />
          <el-table-column label="斑" width="88">
            <template #default="{ row }">
              <span class="dot" :style="{ background: patches.find((p) => p.patch_id === row.patch_id)?.color }" />
              {{ row.patch_id }}
            </template>
          </el-table-column>
          <el-table-column label="SAP" width="96">
            <template #default="{ row }">{{ fmt(row.delta_patch ?? row.sap) }}</template>
          </el-table-column>
          <el-table-column label="亲水分" width="96">
            <template #default="{ row }">{{ fmt(row.hydro_delta) }}</template>
          </el-table-column>
          <el-table-column label="RSA" width="80">
            <template #default="{ row }">{{ fmt(row.rsa) }}</template>
          </el-table-column>
        </el-table>
        <p v-if="tableTab === 'all' && mutations.length > 200" class="hint">仅展示前 200 条，完整结果请下载 CSV。</p>
        <p class="hint">
          「下载全部序列 / 推荐前20」为 FASTA（含 WT 与各突变体 H/L 链）。推荐前20对应湿实验短名单。
        </p>
      </section>
    </template>

    <section v-else-if="job.status === 'running' || job.status === 'queued'" class="waiting">
      <div class="waiting__orb" />
      <div>
        <h2>{{ stageLabel(stage) }}</h2>
        <p>完成后会在这里显示分子表面与疏水斑。页面每 5 秒自动刷新。</p>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.hydro-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1.5rem;
}

.hydro-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: flex-start;

  h1 {
    margin: 0.15rem 0 0.3rem;
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
}

.hydro-top__kicker {
  margin: 0;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #0f766e;
}

.hydro-top__meta {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.hydro-top__actions {
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

  &__idx {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 0.68rem;
    font-weight: 700;
    background: #e2e8f0;
    color: #475569;
  }

  .done {
    border-color: #99f6e4;
    background: #f0fdfa;
    color: #0f766e;

    .stepper__idx {
      background: #0f766e;
      color: #fff;
    }
  }

  .current {
    border-color: #93c5fd;
    background: #eff6ff;
    color: #1d4ed8;
    font-weight: 600;
  }
}

.kpi {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 0.65rem;

  @media (max-width: 1100px) {
    grid-template-columns: repeat(4, 1fr);
  }

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
    margin-bottom: 0.2rem;
  }

  strong {
    font-size: 0.95rem;
    font-weight: 700;
  }
}

.stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 0.9rem;
  min-height: 640px;

  @media (max-width: 1080px) {
    grid-template-columns: 1fr;
  }
}

.stage__view {
  height: 640px;
  min-height: 560px;
}

.rail {
  min-width: 0;
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
  gap: 0.5rem;
  margin-bottom: 0.85rem;

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
  color: #0f766e;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
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

  &:hover,
  &.on {
    border-color: #99f6e4;
    background: #f0fdfa;
  }
}

.patch__swatch {
  width: 10px;
  border-radius: 999px;
  flex-shrink: 0;
}

.patch__body {
  min-width: 0;
  flex: 1;
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
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    font-size: 0.75rem;
  }
}

.patch__meter {
  display: block;
  height: 3px;
  border-radius: 99px;
  background: #e2e8f0;

  .patch__fill {
    display: block;
    height: 100%;
    border-radius: inherit;
  }
}

.patch__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;

  span {
    padding: 0.08rem 0.4rem;
    border-radius: 999px;
    background: #fff;
    border: 1px solid #e2e8f0;
    font-size: 0.68rem;
    color: #475569;
  }
}

.patch__frozen {
  color: #b45309 !important;
  border-color: #fde68a !important;
  background: #fffbeb !important;
}

.mut-flag {
  font-size: 0.72rem;
  font-weight: 600;
  color: #0f766e;

  &[data-ok='false'] {
    color: #b45309;
  }
}

.results {
  padding: 1rem 1.1rem 1.15rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid var(--border);
}

.results__bar {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 0.85rem;
}

.seg {
  display: inline-flex;
  padding: 3px;
  border-radius: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border);

  button {
    border: none;
    background: transparent;
    padding: 0.38rem 0.8rem;
    border-radius: 8px;
    font-size: 0.8rem;
    color: var(--muted);
    cursor: pointer;

    &.on {
      background: #fff;
      color: #0f766e;
      font-weight: 600;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
  }
}

.downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.focus {
  margin: 0 0 0.75rem;
  font-size: 0.82rem;
  color: var(--body);
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 0.3rem;
  vertical-align: middle;
}

.hint {
  margin: 0.5rem 0 0;
  font-size: 0.76rem;
  color: var(--muted);
}

.waiting {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-height: 220px;
  padding: 1.5rem 1.35rem;
  border-radius: 16px;
  border: 1px dashed #99f6e4;
  background: linear-gradient(180deg, #f0fdfa, #fff);

  h2 {
    margin: 0 0 0.3rem;
    font-size: 1.05rem;
  }

  p {
    margin: 0;
    font-size: 0.85rem;
    color: var(--muted);
  }
}

.waiting__orb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #0f766e;
  box-shadow: 0 0 0 8px rgba(15, 118, 110, 0.12);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    transform: scale(0.85);
    box-shadow: 0 0 0 14px rgba(15, 118, 110, 0.05);
  }
}
</style>
