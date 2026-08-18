<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createRasDockingJob,
  deleteRasDockingJob,
  fetchRasDockingJobs,
  uploadRasCandidate,
} from '@/api/rasDocking'
import type { RasDockingJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const project = ref<'rmc6236' | 'rmc6291'>('rmc6236')
const stage = ref('literature')
const system = ref('rmc6291')
const name = ref('')
const candidate = ref<File | null>(null)
const jobs = ref<RasDockingJob[]>([])
const submitting = ref(false)
const activeId = computed(() => route.name === 'ras-docking-job' ? route.params.id : null)

const stages6236 = [
  { value: 'fetch', label: '下载参考结构' },
  { value: 'prepare', label: '准备三元复合物' },
  { value: 'redock', label: '参考配体重对接' },
  { value: 'literature', label: '文献化合物对接' },
  { value: 'screen', label: '候选 SDF 筛选' },
  { value: 'contacts', label: '接触分析' },
]
const stages6291 = [
  { value: 'download', label: '下载结构' },
  { value: 'prepare', label: '准备体系' },
  { value: 'dock', label: '约束重对接' },
]

async function loadList() {
  try { jobs.value = (await fetchRasDockingJobs()).items ?? [] } catch { jobs.value = [] }
}
function onProjectChange() {
  stage.value = project.value === 'rmc6236' ? 'literature' : 'download'
}
function onFileChange(file: { raw?: File }) { candidate.value = file.raw ?? null }
async function submit() {
  if (stage.value === 'screen' && !candidate.value) {
    ElMessage.warning('候选筛选需要上传 SDF 文件'); return
  }
  submitting.value = true
  try {
    const job = stage.value === 'screen'
      ? await uploadRasCandidate(candidate.value!, name.value.trim() || null)
      : await createRasDockingJob({
          name: name.value.trim() || null, project: project.value,
          stage: stage.value, system: system.value,
        })
    await loadList()
    name.value = ''
    candidate.value = null
    router.push({ name: 'ras-docking-job', params: { id: job.id } })
    ElMessage.success('分子对接任务已提交')
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '提交失败') }
  finally { submitting.value = false }
}
function openJob(job: RasDockingJob) { router.push({ name: 'ras-docking-job', params: { id: job.id } }) }
async function removeJob(job: RasDockingJob) {
  try {
    await ElMessageBox.confirm(`确定删除「${job.name || job.id.slice(0, 8)}」吗？`, '删除任务', { type: 'warning' })
    await deleteRasDockingJob(job.id)
    if (activeId.value === job.id) router.push({ name: 'ras-docking' })
    await loadList()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}
function tagType(status: string) { return status === 'done' ? 'success' : status === 'failed' ? 'danger' : 'info' }
onMounted(() => void loadList())
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>RAS 三元复合物对接</h3>
      <p class="field-hint">KRAS + CypA + 小分子配体。MD 验证暂未接入本模块。</p>
      <el-form label-position="top" size="small">
        <el-form-item label="任务名称">
          <el-input v-model="name" placeholder="可选" />
        </el-form-item>
        <el-form-item label="项目">
          <el-select v-model="project" style="width: 100%" @change="onProjectChange">
            <el-option label="RMC-6236（非共价）" value="rmc6236" />
            <el-option label="RMC-6291（Cys12 共价体系）" value="rmc6291" />
          </el-select>
        </el-form-item>
        <el-form-item label="工作阶段">
          <el-select v-model="stage" style="width: 100%">
            <el-option
              v-for="item in project === 'rmc6236' ? stages6236 : stages6291"
              :key="item.value" :label="item.label" :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="project === 'rmc6291'" label="体系">
          <el-input v-model="system" />
        </el-form-item>
        <el-form-item v-if="stage === 'screen'" label="候选分子 SDF" required>
          <el-upload :auto-upload="false" :limit="1" accept=".sdf,.sd,.mol" :on-change="onFileChange">
            <el-button size="small">选择 candidates.sdf</el-button>
          </el-upload>
        </el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">提交对接任务</el-button>
      </el-form>
      <el-divider />
      <div v-for="job in jobs" :key="job.id" class="job-row" :class="{ active: activeId === job.id }" @click="openJob(job)">
        <div class="job-row-main"><strong>{{ job.name || job.id.slice(0, 8) }}</strong><el-tag size="small" :type="tagType(job.status)">{{ statusLabel(job.status) }}</el-tag></div>
        <small>{{ job.params_json?.project }} · {{ job.params_json?.stage }}</small>
        <el-button link type="danger" size="small" @click.stop="removeJob(job)">删除</el-button>
      </div>
    </aside>
    <section class="md-content"><RouterView /></section>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.job-row { padding: .65rem 0; border-bottom: 1px solid var(--border); cursor: pointer; }
.job-row.active { background: rgba(0, 172, 161, .08); }
.job-row-main { display: flex; justify-content: space-between; gap: .5rem; }
.job-row small { color: var(--text-muted); }
</style>
