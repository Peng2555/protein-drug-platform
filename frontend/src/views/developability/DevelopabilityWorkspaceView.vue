<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createDevelopabilityJob,
  deleteDevelopabilityJob,
  fetchDevelopabilityJob,
  fetchDevelopabilityJobs,
  resubmitDevelopabilityJob,
} from '@/api/developability'
import type { DevelopabilityJob } from '@/api/types'
import { EXAMPLE_FASTA, statusLabel } from '@/utils/constants'

const DRAFT_KEY = 'boltz2.developability.draft.v1'

const route = useRoute()
const router = useRouter()
const name = ref('')
const fasta = ref('')
const goal = ref<'hydro' | 'tm' | 'both'>('both')
const freezeCys = ref(true)
const freezeCdr3 = ref(true)
const freezeAllCdrs = ref(false)
const dllThreshold = ref(0)
const maxMutants = ref(19)
const jobs = ref<DevelopabilityJob[]>([])
const submitting = ref(false)
const refreshing = ref(false)
const resubmittingId = ref<string | null>(null)
const activeId = computed(() => route.name === 'developability-job' ? route.params.id : null)
const hasActiveJobs = computed(() => jobs.value.some((j) => ['queued', 'running'].includes(j.status)))
const hasDraft = computed(() => Boolean(fasta.value.trim()))
let listTimer: ReturnType<typeof setInterval> | null = null

function saveDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      name: name.value,
      fasta: fasta.value,
      goal: goal.value,
      freezeCys: freezeCys.value,
      freezeCdr3: freezeCdr3.value,
      freezeAllCdrs: freezeAllCdrs.value,
      dllThreshold: dllThreshold.value,
      maxMutants: maxMutants.value,
    }))
  } catch { /* quota / private mode */ }
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const d = JSON.parse(raw) as Record<string, unknown>
    if (typeof d.name === 'string') name.value = d.name
    if (typeof d.fasta === 'string') fasta.value = d.fasta
    if (d.goal === 'hydro' || d.goal === 'tm' || d.goal === 'both') goal.value = d.goal
    if (typeof d.freezeCys === 'boolean') freezeCys.value = d.freezeCys
    if (typeof d.freezeCdr3 === 'boolean') freezeCdr3.value = d.freezeCdr3
    if (typeof d.freezeAllCdrs === 'boolean') freezeAllCdrs.value = d.freezeAllCdrs
    if (typeof d.dllThreshold === 'number') dllThreshold.value = d.dllThreshold
    if (typeof d.maxMutants === 'number') maxMutants.value = d.maxMutants
  } catch { /* ignore broken draft */ }
}

watch(
  [name, fasta, goal, freezeCys, freezeCdr3, freezeAllCdrs, dllThreshold, maxMutants],
  saveDraft,
)

async function load() {
  refreshing.value = true
  try { jobs.value = (await fetchDevelopabilityJobs()).items ?? [] } catch { jobs.value = [] }
  finally { refreshing.value = false }
}

function startListPoll() {
  if (listTimer) clearInterval(listTimer)
  if (hasActiveJobs.value) listTimer = setInterval(() => void load(), 4000)
}
watch(hasActiveJobs, startListPoll)

async function submit() {
  if (!fasta.value.trim()) { ElMessage.warning('请粘贴抗体 FASTA'); return }
  submitting.value = true
  try {
    const job = await createDevelopabilityJob({
      fasta: fasta.value,
      name: name.value.trim() || null,
      goal: goal.value,
      freeze_cysteine: freezeCys.value,
      freeze_cdr3: freezeCdr3.value,
      freeze_all_cdrs: freezeAllCdrs.value,
      dll_threshold: dllThreshold.value,
      max_mutants_per_site: maxMutants.value,
    })
    await load()
    router.push({ name: 'developability-job', params: { id: job.id } })
    const label = name.value.trim()
    const sameName = label
      ? jobs.value.filter((j) => j.id !== job.id && (j.name || '') === label).length
      : 0
    ElMessage.success(
      sameName
        ? `已作为新任务保存（与已有「${label}」同名，互不覆盖）。表单已保留。`
        : 'ESM-2 打分任务已提交。左侧表单已保留，可直接再提交。',
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败。表单已保留，改完可直接再点提交。')
  } finally {
    submitting.value = false
  }
}

function applyJobToForm(src: DevelopabilityJob) {
  name.value = src.name || ''
  fasta.value = src.fasta_text || ''
  const p = src.params_json || {}
  const g = p.goal
  goal.value = g === 'hydro' || g === 'tm' || g === 'both' ? g : 'both'
  freezeCys.value = p.freeze_cysteine !== false
  freezeCdr3.value = p.freeze_cdr3 !== false
  freezeAllCdrs.value = Boolean(p.freeze_all_cdrs)
  dllThreshold.value = typeof p.dll_threshold === 'number' ? p.dll_threshold : 0
  maxMutants.value = typeof p.max_mutants_per_site === 'number' ? p.max_mutants_per_site : 19
}

async function fillFromJob(job: DevelopabilityJob) {
  const src = job.fasta_text ? job : await fetchDevelopabilityJob(job.id)
  applyJobToForm(src)
  ElMessage.success('已填回序列和参数，可修改后再次提交')
}

async function resubmitSame(job: DevelopabilityJob) {
  resubmittingId.value = job.id
  submitting.value = true
  try {
    const src = job.fasta_text ? job : await fetchDevelopabilityJob(job.id)
    applyJobToForm(src)
    const created = await resubmitDevelopabilityJob(job.id)
    await load()
    router.push({ name: 'developability-job', params: { id: created.id } })
    ElMessage.success('已作为新任务重新提交（不会覆盖原来那一条）')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '再次提交失败。表单已填回，可直接点提交。')
  } finally {
    submitting.value = false
    resubmittingId.value = null
  }
}

function fillExample() { fasta.value = EXAMPLE_FASTA }
function open(job: DevelopabilityJob) { router.push({ name: 'developability-job', params: { id: job.id } }) }

provide('developabilityForm', { fillFromJob, resubmitSame })
async function remove(job: DevelopabilityJob) {
  try {
    await ElMessageBox.confirm(`确定删除「${job.name || job.id.slice(0, 8)}」吗？`, '删除任务', { type: 'warning' })
    await deleteDevelopabilityJob(job.id)
    await load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
function typeOf(status: string) {
  return status === 'done' ? 'success' : status === 'failed' ? 'danger' : 'info'
}
function shortId(id: string) {
  return id.slice(0, 8)
}
function formatTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
onMounted(() => { loadDraft(); void load(); startListPoll() })
onUnmounted(() => { if (listTimer) clearInterval(listTimer) })
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>序列改造</h3>
      <p class="field-hint">ESM-2 3B 先回答：哪些位点可以突变、能换成哪些氨基酸。亲水/Tm 不在这一步做决定。</p>
      <el-form label-position="top" size="small">
        <el-form-item label="任务名称">
          <el-input v-model="name" placeholder="可选；同名也会各存一份，不会覆盖" />
        </el-form-item>
        <el-form-item label="抗体 FASTA" required>
          <el-input v-model="fasta" type="textarea" :rows="8" placeholder=">H&#10;...&#10;>L&#10;..." />
          <el-button link type="primary" size="small" @click="fillExample">填入示例</el-button>
        </el-form-item>
        <el-form-item label="改造目标">
          <el-select v-model="goal" style="width: 100%">
            <el-option label="仅列出可突变（不按亲水/Tm筛）" value="both" />
            <el-option label="后续若做亲水可参考亲水Δ" value="hydro" />
            <el-option label="后续若做稳定可参考 ΔLL" value="tm" />
          </el-select>
        </el-form-item>
        <el-form-item label="保护规则">
          <el-checkbox v-model="freezeCys">冻住 Cys</el-checkbox>
          <el-checkbox v-model="freezeCdr3">冻住 CDR3</el-checkbox>
          <el-checkbox v-model="freezeAllCdrs">冻住全部 CDR</el-checkbox>
        </el-form-item>
        <div class="double">
          <el-form-item label="ΔLL 阈值">
            <el-input-number v-model="dllThreshold" :step="0.1" :min="-2" :max="2" />
          </el-form-item>
          <el-form-item label="每位点最多突变">
            <el-input-number v-model="maxMutants" :min="1" :max="19" />
          </el-form-item>
        </div>
        <el-button type="primary" :loading="submitting && !resubmittingId" @click="submit">提交 ESM-2 打分</el-button>
        <p v-if="hasDraft" class="field-hint keep-hint">提交失败或刷新页面后，序列和参数会留在这里，不必重新粘贴。</p>
      </el-form>
      <el-divider />
      <div class="list-head">
        <span>任务列表</span>
        <el-button size="small" text :loading="refreshing" @click="load">刷新</el-button>
      </div>
      <div
        v-for="job in jobs"
        :key="job.id"
        class="job-row"
        :class="{ active: activeId === job.id }"
        @click="open(job)"
      >
        <div class="job-row-main">
          <strong>{{ job.name || shortId(job.id) }}</strong>
          <el-tag size="small" :type="typeOf(job.status)">{{ statusLabel(job.status) }}</el-tag>
        </div>
        <small>#{{ shortId(job.id) }} · {{ formatTime(job.created_at) }} · {{ job.total_length }} aa</small>
        <div class="job-row-actions">
          <el-button link type="primary" size="small" @click.stop="fillFromJob(job)">填回表单</el-button>
          <el-button
            v-if="job.status === 'failed'"
            link
            type="primary"
            size="small"
            :loading="resubmittingId === job.id"
            @click.stop="resubmitSame(job)"
          >再提交</el-button>
          <el-button link type="danger" size="small" @click.stop="remove(job)">删除</el-button>
        </div>
      </div>
    </aside>
    <section class="md-content"><RouterView /></section>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.double { display: flex; gap: .35rem; }
.double > * { width: 50%; }
.job-row { padding: .65rem 0; border-bottom: 1px solid var(--border); cursor: pointer; }
.job-row.active { background: rgba(0, 172, 161, .08); }
.job-row-main { display: flex; justify-content: space-between; gap: .5rem; }
.job-row small { color: var(--text-muted); }
.job-row-actions { display: flex; flex-wrap: wrap; gap: .15rem; }
.keep-hint { margin: .45rem 0 0; }
.list-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: .35rem; font-weight: 600; }
</style>
