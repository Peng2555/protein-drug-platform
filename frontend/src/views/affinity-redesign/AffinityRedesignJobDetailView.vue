<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Clock, Loading } from '@element-plus/icons-vue'
import {
  downloadAffinityRedesignFile,
  fetchAffinityRedesignJob,
  fetchAffinityRedesignProgress,
  fetchAffinityRedesignRanked,
} from '@/api/affinityRedesign'
import type {
  AffinityRedesignHit,
  AffinityRedesignJob,
  AffinityRedesignProgressOut,
  AffinityRedesignRankedRow,
} from '@/api/types'
import { affinityRedesignStageLabel, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const job = ref<AffinityRedesignJob | null>(null)
const progress = ref<AffinityRedesignProgressOut | null>(null)
const ranked = ref<AffinityRedesignRankedRow[]>([])
const wetlab = ref<AffinityRedesignRankedRow[]>([])
const summary = ref<Record<string, unknown> | null>(null)
const loading = ref(true)
const showRuntimeDetails = ref(true)
const activeLogPanels = ref<string[]>([])
const nowTs = ref(Date.now())
let pollTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const params = computed(() => job.value?.params_json || {})
const entryMode = computed(() =>
  params.value.entry_mode === 'structure' ? '入口 A · 已有复合物' : '入口 B · 仅序列',
)

type PipelineStep = { id: string; match: string[]; label: string; hint: string }

const PIPELINE_STEPS: PipelineStep[] = [
  { id: 'structure', match: ['ensure_structure', 'fold_wt_complex'], label: 'WT 结构', hint: '复合物坐标或 Boltz2 折 WT' },
  { id: 'round1', match: ['round1', 'skip_round1'], label: 'Round1', hint: 'PLM + 结构轨采样' },
  { id: 'boltz2', match: ['rescore', 'boltz2_wt'], label: 'Boltz2 全量', hint: 'WT + 候选复合物折叠' },
  { id: 'rosetta', match: ['rosetta'], label: 'Rosetta', hint: '界面 ΔΔG 排序' },
  { id: 'done', match: ['done'], label: '导出', hint: 'ranked / wetlab' },
]

const currentStage = computed(() => progress.value?.stage || job.value?.stage || 'queued')
const completedStages = computed(() => progress.value?.workflow_status?.stages as string[] | undefined)

function stepState(step: PipelineStep): 'done' | 'active' | 'pending' {
  const stages = completedStages.value || []
  const cur = currentStage.value
  if (step.match.includes('done') && job.value?.status === 'done') return 'done'
  if (step.match.some((k) => stages.includes(k))) {
    if (step.match.includes(cur)) return 'active'
    return 'done'
  }
  if (step.id === 'boltz2' && (cur.startsWith('boltz2') || cur === 'rescore')) return 'active'
  if (step.match.includes(cur)) return 'active'
  const order = PIPELINE_STEPS.map((s) => s.id)
  const curIdx = order.findIndex((id) => {
    const s = PIPELINE_STEPS.find((x) => x.id === id)!
    return s.match.includes(cur) || (id === 'boltz2' && cur.startsWith('boltz2'))
  })
  const stepIdx = order.indexOf(step.id)
  if (curIdx >= 0 && stepIdx < curIdx) return 'done'
  return 'pending'
}

const elapsedSeconds = computed(() => {
  const j = job.value
  if (!j?.started_at) return null
  const start = new Date(j.started_at).getTime()
  if (j.runtime_seconds != null && j.status !== 'running') return Math.round(j.runtime_seconds)
  return Math.max(0, Math.round((nowTs.value - start) / 1000))
})

const boltzPercent = computed(() => {
  const p = progress.value?.progress
  if (p?.boltz2_percent != null) return Number(p.boltz2_percent)
  if (p?.boltz2_current != null && p?.boltz2_total) {
    return Math.min(100, Math.round((100 * Number(p.boltz2_current)) / Number(p.boltz2_total)))
  }
  return 0
})

const showBoltzProgress = computed(() => {
  const cur = currentStage.value
  return cur.startsWith('boltz2') || cur === 'rescore' || progress.value?.progress?.boltz2_total
})

const campaignShort = computed(() => {
  const line = progress.value?.summary_lines?.find((s) => s.startsWith('Campaign:'))
  const raw = line?.replace(/^Campaign:\s*/, '') || ''
  if (!raw) return '—'
  const parts = raw.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts.slice(-2).join('/')
})

const campaignFull = computed(() => {
  const line = progress.value?.summary_lines?.find((s) => s.startsWith('Campaign:'))
  return line?.replace(/^Campaign:\s*/, '') || ''
})

const currentVariant = computed(() => {
  const v = progress.value?.progress?.boltz2_variant
  return v ? String(v).replace(/^H_/, '') : ''
})

type Round1Tiers = { A: string[]; B: string[]; C: string[] }

const round1Tiers = computed<Round1Tiers | null>(() => {
  const section = progress.value?.sections?.find((s) => s.id.includes('round1_result'))
  if (!section?.content) return null
  try {
    const data = JSON.parse(section.content) as { tier_labels?: Round1Tiers }
    const labels = data.tier_labels
    if (labels && (labels.A || labels.B || labels.C)) {
      return {
        A: labels.A || [],
        B: labels.B || [],
        C: labels.C || [],
      }
    }
  } catch {
    return null
  }
  return null
})

const logSections = computed(() =>
  (progress.value?.sections || []).filter(
    (s) =>
      !s.id.includes('round1_result') &&
      s.id !== 'error' &&
      !s.title.endsWith('.log'),
  ),
)

const rawLogSections = computed(() =>
  (progress.value?.sections || []).filter((s) => s.title.endsWith('.log')),
)

type TrackSite = {
  key: string
  chain: string
  position: number
  wt: string
  region: string
  plm: AffinityRedesignHit[]
  structure: AffinityRedesignHit[]
  both: boolean
}

type TrackFilter = 'all' | 'both' | 'plm' | 'structure'
const trackFilter = ref<TrackFilter>('all')

function groupTrackHits(hits: AffinityRedesignHit[]): Map<string, AffinityRedesignHit[]> {
  const map = new Map<string, AffinityRedesignHit[]>()
  for (const hit of hits) {
    const key = `${hit.chain}:${hit.position}`
    const list = map.get(key) || []
    list.push(hit)
    map.set(key, list)
  }
  return map
}

const trackSites = computed<TrackSite[]>(() => {
  const plmHits = progress.value?.plm_hits || []
  const structHits = progress.value?.structure_hits || []
  const plmMap = groupTrackHits(plmHits)
  const structMap = groupTrackHits(structHits)
  const keys = new Set([...plmMap.keys(), ...structMap.keys()])
  const rows: TrackSite[] = []
  for (const key of keys) {
    const plm = plmMap.get(key) || []
    const structure = structMap.get(key) || []
    const sample = plm[0] || structure[0]
    if (!sample) continue
    rows.push({
      key,
      chain: sample.chain,
      position: sample.position,
      wt: sample.wt,
      region: sample.region,
      plm,
      structure,
      both: plm.length > 0 && structure.length > 0,
    })
  }
  rows.sort((a, b) => a.chain.localeCompare(b.chain) || a.position - b.position)
  return rows
})

const filteredTrackSites = computed(() => {
  const rows = trackSites.value
  if (trackFilter.value === 'both') return rows.filter((r) => r.both)
  if (trackFilter.value === 'plm') return rows.filter((r) => r.plm.length && !r.structure.length)
  if (trackFilter.value === 'structure') return rows.filter((r) => r.structure.length && !r.plm.length)
  return rows
})

const trackCounts = computed(() => ({
  plm: progress.value?.plm_hits?.length || 0,
  structure: progress.value?.structure_hits?.length || 0,
  sites: trackSites.value.length,
  both: trackSites.value.filter((r) => r.both).length,
}))

function fmtScore(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return ''
  return n.toFixed(2)
}

async function loadProgress(silent = false) {
  const id = route.params.id as string
  try {
    progress.value = await fetchAffinityRedesignProgress(id)
  } catch (e) {
    if (!silent) ElMessage.error(e instanceof Error ? e.message : '进度加载失败')
  }
}

async function load() {
  const id = route.params.id as string
  try {
    job.value = await fetchAffinityRedesignJob(id)
    await loadProgress(true)
    if (job.value.status === 'done' || job.value.results_json?.ranked) {
      const data = await fetchAffinityRedesignRanked(id)
      ranked.value = data.ranked
      wetlab.value = data.wetlab
      summary.value = data.summary
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function setupPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    if (!job.value || !['queued', 'running'].includes(job.value.status)) {
      if (pollTimer) clearInterval(pollTimer)
      pollTimer = null
      return
    }
    await load()
  }, 5000)
}

watch(
  () => route.params.id,
  async () => {
    loading.value = true
    ranked.value = []
    wetlab.value = []
    summary.value = null
    progress.value = null
    await load()
    setupPolling()
  },
)

onMounted(async () => {
  await load()
  setupPolling()
  clockTimer = setInterval(() => {
    nowTs.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (clockTimer) clearInterval(clockTimer)
})

async function download(name: string) {
  if (!job.value) return
  try {
    await downloadAffinityRedesignFile(job.value.id, name)
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

function fmtDuration(sec: number | null) {
  if (sec == null) return '—'
  if (sec < 60) return `${sec} 秒`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  if (m < 60) return `${m} 分 ${s} 秒`
  const h = Math.floor(m / 60)
  return `${h} 时 ${m % 60} 分`
}

function decisionTagType(decision?: string): 'success' | 'warning' | 'info' | undefined {
  if (decision === 'keep') return 'success'
  if (decision === 'review') return 'warning'
  if (decision === 'drop') return 'info'
  return undefined
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}
</script>

<template>
  <div v-loading="loading" class="ar-detail">
    <template v-if="job">
      <header class="ar-detail__hero">
        <div class="ar-detail__hero-main">
          <span class="ar-detail__badge">亲和力改造</span>
          <h1>{{ job.name || job.id.slice(0, 8) }}</h1>
          <p class="ar-detail__meta">
            #{{ job.id.slice(0, 8) }} · {{ new Date(job.created_at).toLocaleString('zh-CN') }} ·
            {{ entryMode }}
          </p>
        </div>
        <div class="ar-detail__hero-actions">
          <el-tag size="large" :type="statusTagType(job.status)">
            {{ statusLabel(job.status) }}
            <template v-if="job.status === 'running'">
              · {{ affinityRedesignStageLabel(currentStage) }}
            </template>
          </el-tag>
          <el-button size="small" @click="load">刷新</el-button>
          <el-button size="small" @click="router.push({ name: 'affinity-redesign-new' })">新建</el-button>
        </div>
      </header>

      <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" class="ar-detail__alert" />

      <section class="ar-detail__pipeline">
        <div
          v-for="(step, i) in PIPELINE_STEPS"
          :key="step.id"
          class="ar-detail__pipe-step"
          :class="`ar-detail__pipe-step--${stepState(step)}`"
        >
          <div class="ar-detail__pipe-icon">
            <el-icon v-if="stepState(step) === 'done'"><Check /></el-icon>
            <el-icon v-else-if="stepState(step) === 'active'" class="is-spin"><Loading /></el-icon>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div>
            <strong>{{ step.label }}</strong>
            <span>{{ step.hint }}</span>
          </div>
        </div>
      </section>

      <div class="ar-detail__stats">
        <div class="ar-detail__stat">
          <el-icon><Clock /></el-icon>
          <div>
            <span>已运行</span>
            <strong>{{ fmtDuration(elapsedSeconds) }}</strong>
          </div>
        </div>
        <div v-if="progress?.progress?.merged_candidates" class="ar-detail__stat">
          <div>
            <span>Round1 候选</span>
            <strong>{{ progress.progress.merged_candidates }}</strong>
          </div>
        </div>
        <div v-if="progress?.progress?.boltz2_ok != null" class="ar-detail__stat">
          <div>
            <span>Boltz2 成功</span>
            <strong>
              {{ progress.progress.boltz2_ok }}/{{ progress.progress.boltz2_total || progress.progress.boltz2_done || '?' }}
            </strong>
          </div>
        </div>
        <div class="ar-detail__stat ar-detail__stat--wide">
          <div>
            <span>当前阶段</span>
            <strong>{{ affinityRedesignStageLabel(currentStage) }}</strong>
          </div>
        </div>
      </div>

      <section v-if="showBoltzProgress && job.status === 'running'" class="ar-detail__progress-block">
        <div class="ar-detail__progress-head">
          <span>Boltz2 折叠进度</span>
          <span v-if="progress?.progress?.boltz2_current">
            {{ progress.progress.boltz2_current }}/{{ progress.progress.boltz2_total }}
          </span>
        </div>
        <el-progress :percentage="boltzPercent" :stroke-width="10" striped striped-flow />
        <p class="ar-detail__progress-note">Boltz2 与结构预测 fold 共用 GPU 队列，Rosetta 阶段为 CPU。</p>
      </section>

      <section class="ar-detail__runtime">
        <div class="ar-detail__runtime-head">
          <h3>运行详情</h3>
          <el-button size="small" text @click="showRuntimeDetails = !showRuntimeDetails">
            {{ showRuntimeDetails ? '收起' : '展开' }}
          </el-button>
        </div>
        <div v-show="showRuntimeDetails" class="ar-detail__runtime-body">
          <dl class="ar-kv">
            <div>
              <dt>任务 ID</dt>
              <dd class="ar-kv__mono">{{ job.id }}</dd>
            </div>
            <div>
              <dt>入口</dt>
              <dd>{{ entryMode }}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{{ job.started_at ? new Date(job.started_at).toLocaleString('zh-CN') : '—' }}</dd>
            </div>
            <div>
              <dt>Campaign</dt>
              <dd class="ar-kv__mono" :title="campaignFull">{{ campaignShort }}</dd>
            </div>
            <div v-if="currentVariant">
              <dt>当前突变</dt>
              <dd><span class="ar-chip ar-chip--now">{{ currentVariant }}</span></dd>
            </div>
          </dl>

          <div v-if="trackSites.length" class="ar-tracks">
            <div class="ar-tracks__head">
              <div>
                <h4>双轨建议位点</h4>
                <p>
                  PLM {{ trackCounts.plm }} 条 · 结构 {{ trackCounts.structure }} 条 ·
                  {{ trackCounts.sites }} 个位点 · 两轨同点 {{ trackCounts.both }}
                </p>
              </div>
              <div class="ar-tracks__filters">
                <button
                  v-for="opt in [
                    { id: 'all', label: '全部' },
                    { id: 'both', label: '两轨同点' },
                    { id: 'plm', label: '仅 PLM' },
                    { id: 'structure', label: '仅结构' },
                  ]"
                  :key="opt.id"
                  type="button"
                  :class="{ 'is-active': trackFilter === opt.id }"
                  @click="trackFilter = opt.id as TrackFilter"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>
            <div class="ar-sites">
              <article
                v-for="site in filteredTrackSites"
                :key="site.key"
                class="ar-site"
                :class="{ 'ar-site--both': site.both }"
              >
                <div class="ar-site__pos">
                  <strong>{{ site.wt }}{{ site.position }}</strong>
                  <span>{{ site.chain }} · {{ site.region || '—' }}</span>
                </div>
                <div class="ar-site__track">
                  <label>PLM</label>
                  <div class="ar-site__aas">
                    <span
                      v-for="hit in site.plm"
                      :key="'p' + hit.label"
                      class="ar-aa ar-aa--plm"
                      :title="hit.label + (hit.score != null ? ' ΔLL ' + fmtScore(hit.score) : '')"
                    >
                      {{ site.wt }}→{{ hit.mut }}
                      <small v-if="hit.score != null">{{ fmtScore(hit.score) }}</small>
                    </span>
                    <em v-if="!site.plm.length">—</em>
                  </div>
                </div>
                <div class="ar-site__track">
                  <label>结构</label>
                  <div class="ar-site__aas">
                    <span
                      v-for="hit in site.structure"
                      :key="'s' + hit.label"
                      class="ar-aa ar-aa--st"
                      :title="hit.label + (hit.score != null ? ' ΔLL ' + fmtScore(hit.score) : '')"
                    >
                      {{ site.wt }}→{{ hit.mut }}
                      <small v-if="hit.score != null">{{ fmtScore(hit.score) }}</small>
                    </span>
                    <em v-if="!site.structure.length">—</em>
                  </div>
                </div>
              </article>
              <p v-if="!filteredTrackSites.length" class="ar-tracks__empty">当前筛选下没有位点。</p>
            </div>
          </div>

          <div v-if="round1Tiers" class="ar-tiers">
            <div class="ar-tier ar-tier--a">
              <header>
                <strong>A 两轨交集</strong>
                <span>{{ round1Tiers.A.length }}</span>
              </header>
              <div class="ar-tier__chips">
                <span v-for="lab in round1Tiers.A" :key="'A'+lab" class="ar-chip ar-chip--a">{{ lab }}</span>
                <em v-if="!round1Tiers.A.length">无</em>
              </div>
            </div>
            <div class="ar-tier ar-tier--b">
              <header>
                <strong>B 仅结构</strong>
                <span>{{ round1Tiers.B.length }}</span>
              </header>
              <div class="ar-tier__chips">
                <span v-for="lab in round1Tiers.B" :key="'B'+lab" class="ar-chip ar-chip--b">{{ lab }}</span>
                <em v-if="!round1Tiers.B.length">无</em>
              </div>
            </div>
            <div class="ar-tier ar-tier--c">
              <header>
                <strong>C 仅 PLM</strong>
                <span>{{ round1Tiers.C.length }}</span>
              </header>
              <div class="ar-tier__chips">
                <span v-for="lab in round1Tiers.C" :key="'C'+lab" class="ar-chip ar-chip--c">{{ lab }}</span>
                <em v-if="!round1Tiers.C.length">无</em>
              </div>
            </div>
          </div>

          <el-collapse
            v-if="logSections.length || rawLogSections.length"
            v-model="activeLogPanels"
            class="ar-detail__logs"
          >
            <el-collapse-item
              v-for="section in logSections"
              :key="section.id"
              :name="section.id"
              :title="section.title + (section.truncated ? '（末尾）' : '')"
            >
              <pre class="ar-detail__log-pre">{{ section.content }}</pre>
            </el-collapse-item>
            <el-collapse-item
              v-if="rawLogSections.length"
              name="raw-logs"
              title="原始日志"
            >
              <el-collapse>
                <el-collapse-item
                  v-for="section in rawLogSections"
                  :key="section.id"
                  :name="section.id"
                  :title="section.title + (section.truncated ? '（末尾）' : '')"
                >
                  <pre class="ar-detail__log-pre">{{ section.content }}</pre>
                </el-collapse-item>
              </el-collapse>
            </el-collapse-item>
          </el-collapse>
          <p v-else-if="job.status === 'running' || job.status === 'queued'" class="ar-detail__log-empty">
            流水线已启动，日志将在各阶段写入后自动显示。
          </p>
        </div>
      </section>

      <div v-if="summary" class="ar-detail__meta-grid">
        <div><span>候选总数</span>{{ summary.n_merged ?? '—' }}</div>
        <div><span>Boltz2 成功</span>{{ summary.n_boltz2_ok ?? '—' }}</div>
        <div><span>keep</span>{{ summary.n_keep ?? '—' }}</div>
        <div><span>review</span>{{ summary.n_review ?? '—' }}</div>
        <div><span>drop</span>{{ summary.n_drop ?? '—' }}</div>
        <div><span>湿实验短名单</span>{{ summary.n_wetlab ?? wetlab.length }}</div>
      </div>

      <template v-if="job.status === 'done' && ranked.length">
        <div class="ar-detail__file-actions">
          <el-button size="small" type="primary" @click="download('ranked_mutations.csv')">
            下载 ranked_mutations.csv
          </el-button>
          <el-button size="small" @click="download('wetlab_candidates.csv')">湿实验短名单</el-button>
          <el-button size="small" @click="download('structures.zip')">structures.zip</el-button>
          <el-button size="small" @click="download('summary.json')">summary.json</el-button>
        </div>

        <h4 class="ar-detail__table-title">突变体排序</h4>
        <el-table :data="ranked" size="small" stripe max-height="520">
          <el-table-column prop="rank" label="#" width="55" />
          <el-table-column label="decision" width="88">
            <template #default="{ row }">
              <el-tag v-if="row.decision" size="small" :type="decisionTagType(row.decision)">
                {{ row.decision }}
              </el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="tier" label="tier" width="64" />
          <el-table-column prop="label" label="label" min-width="100" />
          <el-table-column prop="chain" label="链" width="52" />
          <el-table-column label="ΔipTM" width="88">
            <template #default="{ row }">{{ fmt(row.delta_iptm) }}</template>
          </el-table-column>
          <el-table-column label="ddG" width="80">
            <template #default="{ row }">{{ fmt(row.ddG) }}</template>
          </el-table-column>
          <el-table-column label="ipTM" width="80">
            <template #default="{ row }">{{ fmt(row.iptm) }}</template>
          </el-table-column>
          <el-table-column prop="wetlab" label="wetlab" width="72" />
          <el-table-column prop="reason" label="reason" min-width="120" show-overflow-tooltip />
        </el-table>
      </template>

      <el-empty v-else-if="job.status === 'done'" description="任务已完成但未找到 ranked_mutations.csv" />
    </template>
  </div>
</template>

<style scoped lang="scss">
.ar-detail {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0.5rem 0 2rem;
}

.ar-detail__hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 1.35rem 1.5rem;
  margin-bottom: 1rem;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: linear-gradient(135deg, #eff6ff 0%, #ecfdf5 100%);

  h1 {
    margin: 0.35rem 0 0.25rem;
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
}

.ar-detail__badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #1d4ed8;
  background: #dbeafe;
  border: 1px solid #93c5fd;
}

.ar-detail__meta {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.ar-detail__hero-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.ar-detail__alert {
  margin-bottom: 1rem;
}

.ar-detail__pipeline {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.5rem;
  margin-bottom: 1rem;

  @media (max-width: 900px) {
    grid-template-columns: 1fr 1fr;
  }
}

.ar-detail__pipe-step {
  display: flex;
  gap: 0.55rem;
  align-items: flex-start;
  padding: 0.75rem 0.85rem;
  border-radius: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
  font-size: 0.74rem;

  strong {
    display: block;
    font-size: 0.82rem;
    margin-bottom: 0.1rem;
  }

  span {
    color: var(--muted);
    line-height: 1.45;
  }

  &--done {
    border-color: #a7f3d0;
    background: #f0fdf4;
  }

  &--active {
    border-color: #93c5fd;
    background: #eff6ff;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
  }

  &--pending {
    opacity: 0.72;
  }
}

.ar-detail__pipe-icon {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
  background: #9ca3af;

  .ar-detail__pipe-step--done & {
    background: #059669;
  }

  .ar-detail__pipe-step--active & {
    background: #2563eb;
  }
}

.is-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.ar-detail__stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.65rem;
  margin-bottom: 1rem;
}

.ar-detail__stat {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.75rem 0.9rem;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #fff;

  span {
    display: block;
    font-size: 0.68rem;
    color: var(--muted);
  }

  strong {
    font-size: 0.95rem;
  }

  &--wide {
    grid-column: span 2;

    @media (max-width: 600px) {
      grid-column: span 1;
    }
  }
}

.ar-detail__progress-block {
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
  border-radius: 14px;
  border: 1px solid #bfdbfe;
  background: #f8fafc;
}

.ar-detail__progress-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
}

.ar-detail__progress-note {
  margin: 0.5rem 0 0;
  font-size: 0.76rem;
  color: var(--muted);
}

.ar-detail__runtime {
  margin-bottom: 1rem;
  padding: 1.05rem 1.2rem 1.15rem;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: #fff;
}

.ar-detail__runtime-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.85rem;

  h3 {
    margin: 0;
    font-size: 0.95rem;
  }
}

.ar-kv {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem 1.25rem;
  margin: 0 0 1.1rem;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }

  > div {
    min-width: 0;
  }

  dt {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #9ca3af;
    margin-bottom: 0.18rem;
  }

  dd {
    margin: 0;
    font-size: 0.86rem;
    color: #111827;
    word-break: break-all;
  }
}

.ar-kv__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.78rem;
  color: #4b5563;
}

.ar-tracks {
  margin: 0 0 1rem;
  padding: 0.85rem 0.9rem 0.95rem;
  border-radius: 14px;
  border: 1px solid #dbeafe;
  background: #f8fbff;
}

.ar-tracks__head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: flex-start;
  margin-bottom: 0.75rem;

  h4 {
    margin: 0;
    font-size: 0.92rem;
    font-weight: 800;
  }

  p {
    margin: 0.2rem 0 0;
    font-size: 0.75rem;
    color: #6b7280;
  }
}

.ar-tracks__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;

  button {
    border: 1px solid #e5e7eb;
    background: #fff;
    color: #4b5563;
    border-radius: 999px;
    padding: 0.18rem 0.65rem;
    font-size: 0.72rem;
    cursor: pointer;

    &.is-active {
      background: #1d4ed8;
      border-color: #1d4ed8;
      color: #fff;
    }
  }
}

.ar-tracks__empty {
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
  color: #9ca3af;
}

.ar-sites {
  display: grid;
  gap: 0.5rem;
}

.ar-site {
  display: grid;
  grid-template-columns: 108px 1fr 1fr;
  gap: 0.55rem 0.75rem;
  padding: 0.6rem 0.7rem;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #e5e7eb;

  &--both {
    border-color: #86efac;
    background: #f0fdf4;
  }
}

.ar-site__pos {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.15rem;

  strong {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 1.05rem;
    letter-spacing: -0.03em;
  }

  span {
    font-size: 0.68rem;
    color: #6b7280;
  }
}

.ar-site__track {
  min-width: 0;

  label {
    display: block;
    font-size: 0.68rem;
    font-weight: 700;
    color: #6b7280;
    margin-bottom: 0.28rem;
  }
}

.ar-site__aas {
  display: flex;
  flex-wrap: wrap;
  gap: 0.28rem;

  em {
    font-style: normal;
    color: #d1d5db;
    font-size: 0.8rem;
  }
}

.ar-aa {
  display: inline-flex;
  align-items: baseline;
  gap: 0.22rem;
  padding: 0.1rem 0.42rem;
  border-radius: 999px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.72rem;
  font-weight: 700;
  border: 1px solid transparent;

  small {
    font-weight: 500;
    opacity: 0.75;
  }

  &--plm {
    color: #6b21a8;
    background: #f3e8ff;
    border-color: #d8b4fe;
  }

  &--st {
    color: #1e40af;
    background: #dbeafe;
    border-color: #93c5fd;
  }
}

@media (max-width: 760px) {
  .ar-site {
    grid-template-columns: 1fr;
  }
}

.ar-tiers {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.65rem;
  margin-bottom: 0.9rem;
}

.ar-tier {
  border-radius: 12px;
  padding: 0.7rem 0.85rem 0.8rem;
  border: 1px solid #e5e7eb;
  background: #f9fafb;

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;

    strong {
      font-size: 0.8rem;
    }

    span {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 0.08rem 0.45rem;
      border-radius: 999px;
      background: #fff;
      border: 1px solid #e5e7eb;
    }
  }

  &--a {
    background: #f0fdf4;
    border-color: #bbf7d0;
  }

  &--b {
    background: #eff6ff;
    border-color: #bfdbfe;
  }

  &--c {
    background: #faf5ff;
    border-color: #e9d5ff;
  }
}

.ar-tier__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;

  em {
    font-style: normal;
    font-size: 0.76rem;
    color: #9ca3af;
  }
}

.ar-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  border: 1px solid transparent;

  &--a {
    color: #065f46;
    background: #d1fae5;
    border-color: #a7f3d0;
  }

  &--b {
    color: #1e40af;
    background: #dbeafe;
    border-color: #93c5fd;
  }

  &--c {
    color: #6b21a8;
    background: #f3e8ff;
    border-color: #d8b4fe;
  }

  &--now {
    color: #9a3412;
    background: #ffedd5;
    border-color: #fdba74;
  }
}

.ar-detail__logs {
  --el-collapse-border-color: #e5e7eb;
}

.ar-detail__log-pre {
  margin: 0;
  padding: 0.7rem 0.8rem;
  max-height: 240px;
  overflow: auto;
  font-size: 0.7rem;
  line-height: 1.5;
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.ar-detail__log-empty {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.ar-detail__meta-grid {
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

.ar-detail__file-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 1rem 0;
}

.ar-detail__table-title {
  margin: 0 0 0.65rem;
  font-size: 0.95rem;
}
</style>
