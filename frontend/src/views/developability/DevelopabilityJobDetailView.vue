<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadDevelopabilityFile, fetchDevelopabilityJob } from '@/api/developability'
import type {
  DevelopabilityJob,
  DevelopabilityResidue,
} from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const job = ref<DevelopabilityJob | null>(null)
const chainId = ref('')
const selectedIndex = ref<number | null>(null)
const onlyFr = ref(false)
const formCtl = inject<{
  fillFromJob: (job: DevelopabilityJob) => Promise<void>
  resubmitSame: (job: DevelopabilityJob) => Promise<void>
}>('developabilityForm')
const resubmitting = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const results = computed(() => job.value?.results_json as Record<string, unknown> | null)
const dllCut = computed(() => Number(results.value?.dll_threshold ?? 0))
const maxwell = computed(() => (results.value?.maxwell as Record<string, unknown> | undefined) ?? null)
const maxwellSkipped = computed(() => (maxwell.value?.skipped as string | undefined) ?? '')
const maxwellWarnings = computed(() => (maxwell.value?.warnings as string[] | undefined) ?? [])
const chains = computed(() => (results.value?.chains as Array<Record<string, unknown>> | undefined) ?? [])
const currentChain = computed(() => chains.value.find((c) => c.chain_id === chainId.value) ?? chains.value[0] ?? null)
const residues = computed(() => (currentChain.value?.residues as DevelopabilityResidue[] | undefined) ?? [])
const selected = computed(() => residues.value.find((r) => r.index === selectedIndex.value) ?? null)

type SiteRow = {
  index: number
  kabat: string
  aa: string
  region: string
  allowed: string[]
  allowedLabel: string
  bestDll: number | null
  bestMaxwell: number | null
}

const siteRows = computed((): SiteRow[] => {
  return residues.value
    .filter((r) => r.tier === 'candidate')
    .map((r) => {
      const allowed = (r.aa_scores || [])
        .filter((s) => !s.is_wt && s.aa !== 'C' && s.dll >= dllCut.value)
        .sort((a, b) => b.dll - a.dll)
        .map((s) => s.aa)
      return {
        index: r.index,
        kabat: r.kabat,
        aa: r.aa,
        region: r.region,
        allowed,
        allowedLabel: allowed.join(' / ') || '—',
        bestDll: r.best_dll,
        bestMaxwell: r.best_maxwell_ddg ?? null,
      }
    })
    .filter((row) => onlyFr.value ? row.region.startsWith('FR') : true)
})

const selectedAllowed = computed(() => {
  if (!selected.value) return []
  return (selected.value.aa_scores || [])
    .filter((s) => !s.is_wt && s.aa !== 'C' && s.dll >= dllCut.value)
    .sort((a, b) => b.dll - a.dll)
})

async function load() {
  try { job.value = await fetchDevelopabilityJob(route.params.id as string) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '加载失败') }
}
function poll() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) timer = setInterval(() => void load(), 4000)
}
watch(() => job.value?.status, poll)
watch(() => route.params.id, async () => { selectedIndex.value = null; await load() })
watch(chains, (list) => {
  if (!list.length) return
  if (!list.some((c) => c.chain_id === chainId.value)) chainId.value = String(list[0].chain_id)
}, { immediate: true })
onMounted(async () => { await load(); poll() })
onUnmounted(() => { if (timer) clearInterval(timer) })

function tierClass(tier: string) {
  if (tier === 'freeze') return 'cell-freeze'
  if (tier === 'candidate') return 'cell-cand'
  return 'cell-avoid'
}
function pickResidue(res: DevelopabilityResidue) {
  selectedIndex.value = res.index
}
function pickSite(row: SiteRow) {
  selectedIndex.value = row.index
}
async function download(name: string) {
  if (!job.value) return
  try { await downloadDevelopabilityFile(job.value.id, name) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '下载失败') }
}
async function fillForm() {
  if (!job.value || !formCtl) return
  await formCtl.fillFromJob(job.value)
}
async function resubmit() {
  if (!job.value || !formCtl) return
  resubmitting.value = true
  try { await formCtl.resubmitSame(job.value) }
  finally { resubmitting.value = false }
}
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div>
        <h2>{{ job.name || job.id }}</h2>
        <p>
          #{{ job.id.slice(0, 8) }} · {{ new Date(job.created_at).toLocaleString('zh-CN') }}
          · ESM-2 3B + MAXWELL · {{ results?.goal || job.params_json?.goal }} · {{ job.stage }}
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" @click="fillForm">填回表单</el-button>
        <el-button
          v-if="job.status === 'failed' || job.status === 'done'"
          size="small"
          type="primary"
          :loading="resubmitting"
          @click="resubmit"
        >用相同参数再提交</el-button>
        <el-tag>{{ statusLabel(job.status) }}</el-tag>
      </div>
    </div>
    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <p v-if="job.status === 'failed'" class="hint">
      失败任务的序列和参数还在。点「填回表单」可改参数后提交，或点「用相同参数再提交」直接重跑。
    </p>
    <p>耗时：{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</p>

    <template v-if="job.status === 'done' && results">
      <el-alert type="info" :closable="false" title="绿色位点可以突变；矩阵上同时给出 ESM-2 ΔLL（越高越好）和 MAXWELL ΔΔG（越低越稳）。灰色位点不建议动，冻住位点被保护规则排除。" class="note" />
      <el-alert
        v-if="maxwellSkipped"
        type="warning"
        :closable="false"
        :title="`MAXWELL 未运行：${maxwellSkipped}`"
        class="note"
      />
      <el-alert
        v-for="(w, i) in maxwellWarnings"
        :key="i"
        type="warning"
        :closable="false"
        :title="w"
        class="note"
      />
      <p class="stats">
        本链可突变位点 {{ siteRows.length }} 个。ΔLL ≥ {{ dllCut }} 的非 Cys 替换均列出；ΔΔG 为并列参考，不改变候选位点。
      </p>
      <div class="file-actions">
        <el-button size="small" type="primary" @click="download('candidates.csv')">导出候选 CSV</el-button>
        <el-button size="small" @click="download('candidates.json')">导出 JSON</el-button>
        <el-button size="small" @click="download('summary.json')">下载完整结果</el-button>
      </div>

      <div class="chain-tabs">
        <el-button
          v-for="ch in chains"
          :key="String(ch.chain_id)"
          size="small"
          :type="chainId === ch.chain_id ? 'primary' : 'default'"
          @click="chainId = String(ch.chain_id); selectedIndex = null"
        >
          链 {{ ch.chain_id }} · {{ ch.length }} aa
          <span v-if="ch.domain">（{{ ch.domain }}）</span>
        </el-button>
      </div>

      <h4>序列地图</h4>
      <p class="legend">
        <span class="swatch freeze" />冻住
        <span class="swatch cand" />可突变
        <span class="swatch avoid" />不建议
      </p>
      <div class="seq-map">
        <button
          v-for="res in residues"
          :key="res.index"
          type="button"
          class="aa-cell"
          :class="[tierClass(res.tier), { selected: selectedIndex === res.index }]"
          :title="`${res.region} ${res.aa}${res.index}${res.kabat && String(res.kabat) !== String(res.index) ? ` (Kabat ${res.kabat})` : ''}  ${res.tier}`"
          @click="pickResidue(res)"
        >
          {{ res.aa }}
          <small>{{ res.index }}</small>
        </button>
      </div>

      <div v-if="selected" class="matrix-card">
        <h4>
          {{ currentChain?.chain_id }}:{{ selected.aa }}{{ selected.index }}
          · {{ selected.region }}
          · {{ selected.tier === 'freeze' ? '冻住（不可突变）' : selected.tier === 'candidate' ? '可以突变' : '不建议突变' }}
        </h4>
        <p v-if="selected.freeze_reason" class="hint">保护原因：{{ selected.freeze_reason }}</p>
        <p v-else-if="selectedAllowed.length" class="hint">
          可替换为：<strong>{{ selectedAllowed.map((s) => s.aa).join(' / ') }}</strong>
        </p>
        <p v-else class="hint">当前阈值下没有比野生型更好的替换。</p>
        <div class="aa-grid">
          <div
            v-for="row in selected.aa_scores"
            :key="row.aa"
            class="aa-score"
            :class="{ wt: row.is_wt, good: !row.is_wt && row.dll >= dllCut && row.aa !== 'C', bad: !row.is_wt && (row.dll < dllCut || row.aa === 'C') }"
          >
            <strong>{{ row.aa }}</strong>
            <span>ΔLL {{ row.dll >= 0 ? '+' : '' }}{{ row.dll.toFixed(2) }}</span>
            <span v-if="row.maxwell_ddg != null" :class="{ stab: row.maxwell_ddg < 0 }">
              ΔΔG {{ row.maxwell_ddg.toFixed(2) }}
            </span>
            <span v-else class="muted">ΔΔG —</span>
          </div>
        </div>
      </div>

      <div class="table-head">
        <h4>可突变位点及允许的氨基酸</h4>
        <div class="filters">
          <el-checkbox v-model="onlyFr">只看框架</el-checkbox>
        </div>
      </div>
      <el-table :data="siteRows" size="small" border max-height="480" highlight-current-row @row-click="pickSite">
        <el-table-column label="位点" width="120">
          <template #default="{ row }">{{ currentChain?.chain_id }}:{{ row.aa }}{{ row.index }}</template>
        </el-table-column>
        <el-table-column prop="region" label="区域" width="90" />
        <el-table-column prop="allowedLabel" label="可突变成" min-width="240" />
        <el-table-column prop="bestDll" label="最佳 ΔLL" width="110" />
        <el-table-column prop="bestMaxwell" label="最佳 ΔΔG" width="120">
          <template #default="{ row }">{{ row.bestMaxwell == null ? '—' : Number(row.bestMaxwell).toFixed(2) }}</template>
        </el-table-column>
      </el-table>
    </template>
  </div>
  <el-empty v-else description="任务不存在或正在加载" />
</template>

<style scoped lang="scss">
.detail-panel { padding: 1.5rem; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; }
.head-actions { display: flex; align-items: center; gap: .5rem; }
.detail-head h2 { margin: 0 0 .35rem; }
.detail-head p, .hint, .stats { color: var(--text-muted); }
.note { margin: .75rem 0; }
.file-actions, .chain-tabs, .legend, .filters { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: .75rem 0; }
.seq-map { display: flex; flex-wrap: wrap; gap: 3px; margin: .5rem 0 1rem; }
.aa-cell {
  width: 28px; height: 36px; border: 1px solid var(--border); border-radius: 4px;
  background: #fff; cursor: pointer; font-size: .78rem; padding: 0; line-height: 1.1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  small { font-size: .55rem; color: var(--text-muted); }
}
.aa-cell.selected { outline: 2px solid var(--bio-green); }
.cell-freeze { background: #e5e7eb; color: #6b7280; }
.cell-cand { background: #d1fae5; }
.cell-avoid { background: #e0e7ff; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: .2rem; }
.swatch.freeze { background: #e5e7eb; }
.swatch.cand { background: #d1fae5; }
.swatch.avoid { background: #e0e7ff; }
.matrix-card { margin: 1rem 0; padding: 1rem; border: 1px solid var(--border); border-radius: 8px; }
.aa-grid { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: .4rem; }
.aa-score {
  border: 1px solid var(--border); border-radius: 6px; padding: .35rem; text-align: center; font-size: .78rem;
  display: flex; flex-direction: column; gap: .1rem;
}
.aa-score.wt { background: #111827; color: #fff; }
.aa-score.good { background: #ecfdf5; }
.aa-score.bad { background: #f8fafc; color: #94a3b8; }
.aa-score .stab { color: #047857; font-weight: 600; }
.aa-score .muted { color: inherit; opacity: .7; }
.aa-score.wt .stab { color: #6ee7b7; }
.table-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
</style>
