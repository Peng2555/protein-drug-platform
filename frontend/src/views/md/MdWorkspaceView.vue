<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import { createMdJob, deleteMdJob, uploadMdStructure } from '@/api/md'
import type { Job, MdJob } from '@/api/types'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { MD_STAGE_LABELS, statusLabel } from '@/utils/constants'

const router = useRouter()
const route = useRoute()
const foldStore = useFoldTasksStore()

const submitMode = ref<'parent' | 'upload'>('parent')
const parentJobId = ref('')
const parentOptions = ref<Job[]>([])
const mdName = ref('')
const productionNs = ref(10)
const replicas = ref(1)
const antigenChain = ref('A')
const binderChain = ref('H')
const uploadFile = ref<File | null>(null)
const submitting = ref(false)

const activeMdId = computed(() =>
  route.name === 'md-job' ? (route.params.id as string) : null,
)

async function loadParentOptions() {
  const data = await fetchJobs(100, true)
  parentOptions.value = data.items.filter(
    (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
  )
}

async function loadMdList() {
  await foldStore.refreshMdTasks()
}

function onUploadChange(uploadFileArg: { raw?: File }) {
  uploadFile.value = uploadFileArg.raw || null
}

async function submitMd() {
  submitting.value = true
  try {
    let job: MdJob
    if (submitMode.value === 'upload') {
      if (!uploadFile.value) {
        ElMessage.warning('请上传结构文件')
        return
      }
      job = await uploadMdStructure(uploadFile.value, {
        name: mdName.value.trim() || null,
        production_ns: productionNs.value,
        replicas: replicas.value,
        antigen_chain: antigenChain.value,
        binder_chain: binderChain.value,
      })
    } else {
      if (!parentJobId.value) {
        ElMessage.warning('请选择来源折叠任务')
        return
      }
      job = await createMdJob({
        parent_job_id: parentJobId.value,
        name: mdName.value.trim() || null,
        production_ns: productionNs.value,
        replicas: replicas.value,
        antigen_chain: antigenChain.value,
        binder_chain: binderChain.value,
      })
    }
    mdName.value = ''
    uploadFile.value = null
    await loadMdList()
    foldStore.startPolling()
    router.push({ name: 'md-job', params: { id: job.id } })
    ElMessage.success('MD 任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

function openMdJob(job: MdJob) {
  router.push({ name: 'md-job', params: { id: job.id } })
}

async function onDeleteMd(job: MdJob) {
  const label = job.name || job.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(`确定删除 MD 任务「${label}」吗？`, '删除任务', { type: 'warning' })
    await deleteMdJob(job.id)
    if (activeMdId.value === job.id) router.push({ name: 'md' })
    await loadMdList()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

onMounted(async () => {
  const parent = route.query.parent
  if (typeof parent === 'string') parentJobId.value = parent
  await Promise.all([loadParentOptions(), loadMdList()])
  foldStore.startPolling()
})
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>提交 MD 验证</h3>
      <el-form label-position="top" size="small">
        <el-form-item label="来源">
          <el-radio-group v-model="submitMode">
            <el-radio value="parent">折叠任务</el-radio>
            <el-radio value="upload">上传结构</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="submitMode === 'parent'" label="折叠任务">
          <el-select v-model="parentJobId" placeholder="选择已完成任务" filterable style="width: 100%">
            <el-option
              v-for="j in parentOptions"
              :key="j.id"
              :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
              :value="j.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="结构文件 (.cif / .pdb)">
          <el-upload
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            accept=".cif,.pdb"
            @change="onUploadChange"
          >
            <el-button size="small">选择文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="任务名称（可选）">
          <el-input v-model="mdName" />
        </el-form-item>
        <div class="inline-fields">
          <el-form-item label="生产 (ns)">
            <el-input-number v-model="productionNs" :min="0.1" :max="500" :step="1" />
          </el-form-item>
          <el-form-item label="复本数">
            <el-input-number v-model="replicas" :min="1" :max="5" />
          </el-form-item>
        </div>
        <div class="inline-fields">
          <el-form-item label="抗原链">
            <el-input v-model="antigenChain" style="width: 70px" />
          </el-form-item>
          <el-form-item label="结合链">
            <el-input v-model="binderChain" style="width: 70px" />
          </el-form-item>
        </div>
        <el-button type="primary" size="small" :loading="submitting" @click="submitMd">
          提交 MD
        </el-button>
      </el-form>

      <div class="task-list-section">
        <div class="task-list-head">
          <h3>MD 任务</h3>
          <el-button size="small" text @click="loadMdList">刷新</el-button>
        </div>
        <div v-if="!foldStore.mdJobs.length" class="empty-state">暂无 MD 任务</div>
        <div v-else class="task-list">
          <div
            v-for="j in foldStore.mdJobs"
            :key="j.id"
            class="job-item task-item"
            :class="{ active: activeMdId === j.id }"
            @click="openMdJob(j)"
          >
            <div class="job-item-top">
              <div class="title">
                <span class="task-kind-badge kind-md">MD</span>
                {{ j.name || j.id.slice(0, 8) }}
              </div>
              <div class="job-item-actions" @click.stop>
                <el-tag :type="statusTagType(j.status)" size="small">
                  {{ statusLabel(j.status) }}
                </el-tag>
                <button type="button" class="job-delete-btn" @click="onDeleteMd(j)">×</button>
              </div>
            </div>
            <div class="meta">
              GROMACS MD
              <template v-if="j.stage"> · {{ MD_STAGE_LABELS[j.stage] || j.stage }}</template>
              · {{ formatTime(j.created_at) }}
            </div>
          </div>
        </div>
      </div>
    </aside>

    <div class="fold-main">
      <RouterView />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';

.kind-md {
  background: #ede9fe;
  color: #6d28d9;
}

.inline-fields {
  display: flex;
  gap: 0.75rem;
}

h3 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  color: var(--title);
}
</style>
