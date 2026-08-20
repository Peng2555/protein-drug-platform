<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import {
  createDevelopabilityJob,
  fetchDevelopabilityJob,
  resubmitDevelopabilityJob,
  uploadDevelopabilityJob,
} from '@/api/developability'
import type { DevelopabilityJob, Job } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { EXAMPLE_FASTA } from '@/utils/constants'

const DRAFT_KEY = 'boltz2.developability.draft.v1'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()

const name = ref('')
const fasta = ref('')
const goal = ref<'hydro' | 'tm' | 'both'>('both')
const freezeCys = ref(true)
const freezeCdr3 = ref(true)
const freezeAllCdrs = ref(false)
const dllThreshold = ref(0)
const maxMutants = ref(19)
const runMaxwell = ref(true)
const structureMode = ref<'none' | 'fold_job' | 'upload'>('none')
const foldJobId = ref('')
const foldOptions = ref<Job[]>([])
const uploadFile = ref<File | null>(null)
const submitting = ref(false)
const resubmittingId = ref<string | null>(null)
const hasDraft = computed(() => Boolean(fasta.value.trim()))

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
      runMaxwell: runMaxwell.value,
      structureMode: structureMode.value,
      foldJobId: foldJobId.value,
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
    if (typeof d.runMaxwell === 'boolean') runMaxwell.value = d.runMaxwell
    if (d.structureMode === 'none' || d.structureMode === 'fold_job' || d.structureMode === 'upload') {
      structureMode.value = d.structureMode
    }
    if (typeof d.foldJobId === 'string') foldJobId.value = d.foldJobId
  } catch { /* ignore broken draft */ }
}

watch(
  [name, fasta, goal, freezeCys, freezeCdr3, freezeAllCdrs, dllThreshold, maxMutants, runMaxwell, structureMode, foldJobId],
  saveDraft,
)

async function loadFoldOptions() {
  try {
    const data = await fetchJobs(100, true)
    foldOptions.value = data.items.filter(
      (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
    )
  } catch {
    foldOptions.value = []
  }
}

function onUploadChange(uploadFileArg: { raw?: File }) {
  uploadFile.value = uploadFileArg.raw || null
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
  runMaxwell.value = p.run_maxwell !== false
  if (typeof p.fold_job_id === 'string' && p.fold_job_id) {
    structureMode.value = 'fold_job'
    foldJobId.value = p.fold_job_id
  } else if (src.params_json && typeof src.params_json.structure_path === 'string') {
    structureMode.value = 'none'
  }
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
    await moduleJobs.refreshDevelopability()
    router.push({ name: 'developability-task', params: { id: created.id } })
    ElMessage.success('已作为新任务重新提交（不会覆盖原来那一条）')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '再次提交失败。表单已填回，可直接点提交。')
  } finally {
    submitting.value = false
    resubmittingId.value = null
  }
}

provide('developabilityForm', { fillFromJob, resubmitSame })

async function submit() {
  if (!fasta.value.trim()) { ElMessage.warning('请粘贴抗体 FASTA'); return }
  if (runMaxwell.value && structureMode.value === 'fold_job' && !foldJobId.value) {
    ElMessage.warning('请选择已完成的折叠任务，或改成「这次不跑」')
    return
  }
  if (runMaxwell.value && structureMode.value === 'upload' && !uploadFile.value) {
    ElMessage.warning('请上传 PDB/CIF，或改成「这次不跑」')
    return
  }
  submitting.value = true
  try {
    const wantMaxwell = runMaxwell.value && structureMode.value !== 'none'
    const body = {
      fasta: fasta.value,
      name: name.value.trim() || null,
      goal: goal.value,
      freeze_cysteine: freezeCys.value,
      freeze_cdr3: freezeCdr3.value,
      freeze_all_cdrs: freezeAllCdrs.value,
      dll_threshold: dllThreshold.value,
      max_mutants_per_site: maxMutants.value,
      run_maxwell: wantMaxwell,
      fold_job_id: structureMode.value === 'fold_job' ? (foldJobId.value || null) : null,
    }
    const job = structureMode.value === 'upload' && uploadFile.value
      ? await uploadDevelopabilityJob(uploadFile.value, body)
      : await createDevelopabilityJob(body)
    await moduleJobs.refreshDevelopability()
    router.push({ name: 'developability-task', params: { id: job.id } })
    const label = name.value.trim()
    const sameName = label
      ? moduleJobs.developabilityJobs.filter((j) => j.id !== job.id && (j.name || '') === label).length
      : 0
    ElMessage.success(
      sameName
        ? `已作为新任务保存（与已有「${label}」同名，互不覆盖）。表单已保留。`
        : '打分任务已提交。ESM-2 与 MAXWELL 相互独立；无结构时只跑 ESM-2。表单已保留。',
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败。表单已保留，改完可直接再点提交。')
  } finally {
    submitting.value = false
  }
}

function fillExample() { fasta.value = EXAMPLE_FASTA }

async function handleRouteQuery() {
  const fillId = typeof route.query.fill === 'string' ? route.query.fill : null
  const resubmitId = typeof route.query.resubmit === 'string' ? route.query.resubmit : null
  if (!fillId && !resubmitId) return
  try {
    if (resubmitId) {
      const job = await fetchDevelopabilityJob(resubmitId)
      await resubmitSame(job)
    } else if (fillId) {
      const job = await fetchDevelopabilityJob(fillId)
      await fillFromJob(job)
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载任务失败')
  } finally {
    if (fillId || resubmitId) {
      router.replace({ name: 'developability-new' })
    }
  }
}

watch(() => route.query, () => { void handleRouteQuery() })

onMounted(() => {
  loadDraft()
  void loadFoldOptions()
  void moduleJobs.refreshDevelopability()
  void handleRouteQuery()
})
</script>

<template>
  <div class="developability-new page-card">
    <header class="developability-new__head">
      <h1>新建改造</h1>
      <p>ESM-2 3B 与 Venus-MAXWELL 并列打分：ΔLL 管「序列上像不像」，ΔΔG 管「结构上稳不稳」。候选位点仍由 ESM-2 决定。</p>
    </header>
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
      <el-form-item label="Venus-MAXWELL（结构 ΔΔG）">
        <el-checkbox v-model="runMaxwell">同时跑 MAXWELL</el-checkbox>
        <p class="field-hint">需要抗体链坐标（折叠任务或 PDB/CIF）。没有结构时仍然只跑 ESM-2。</p>
      </el-form-item>
      <el-form-item v-if="runMaxwell" label="结构来源">
        <el-radio-group v-model="structureMode">
          <el-radio value="none">仅 ESM-2（无结构）</el-radio>
          <el-radio value="fold_job">已有折叠任务</el-radio>
          <el-radio value="upload">上传 PDB/CIF</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="runMaxwell && structureMode === 'fold_job'" label="折叠任务">
        <el-select v-model="foldJobId" placeholder="选择已完成任务" filterable style="width: 100%">
          <el-option
            v-for="j in foldOptions"
            :key="j.id"
            :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
            :value="j.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="runMaxwell && structureMode === 'upload'" label="结构文件">
        <el-upload
          :auto-upload="false"
          :show-file-list="true"
          :limit="1"
          accept=".cif,.mmcif,.pdb"
          @change="onUploadChange"
        >
          <el-button size="small">选择文件</el-button>
        </el-upload>
      </el-form-item>
      <el-button type="primary" :loading="submitting && !resubmittingId" @click="submit">提交打分</el-button>
      <p v-if="hasDraft" class="field-hint keep-hint">提交失败或刷新页面后，序列和参数会留在这里，不必重新粘贴。</p>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.developability-new {
  padding: 1.15rem 1.25rem 1.4rem;
}

.developability-new__head {
  margin-bottom: 1rem;

  h1 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--title);
  }

  p {
    margin: 0.35rem 0 0;
    font-size: 0.84rem;
    color: var(--muted);
  }
}

.double {
  display: flex;
  gap: 0.35rem;

  > * {
    width: 50%;
  }
}

.keep-hint {
  margin: 0.45rem 0 0;
}
</style>
