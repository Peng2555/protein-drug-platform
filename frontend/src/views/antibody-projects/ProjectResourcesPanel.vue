<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createJobLink,
  downloadArtifact,
  fetchArtifacts,
  fetchCandidates,
  fetchJobLinks,
  fetchVersions,
  uploadArtifact,
  type AntibodyCandidate,
  type AntibodyVersion,
  type ProjectArtifact,
  type ProjectJobLink,
} from '@/api/antibodyProjects'

const props = defineProps<{ projectId: string }>()
const candidates = ref<AntibodyCandidate[]>([])
const versions = ref<AntibodyVersion[]>([])
const artifacts = ref<ProjectArtifact[]>([])
const jobLinks = ref<ProjectJobLink[]>([])
const selectedFile = ref<File | null>(null)
const saving = ref(false)
const showUpload = ref(false)
const showJob = ref(false)
const uploadForm = reactive({ category: 'other', version_id: '' })
const jobForm = reactive({ version_id: '', job_id: '', purpose: '' })

const categoryText: Record<string, string> = {
  sequence: '序列',
  structure: '结构',
  experiment: '实验',
  job: '计算',
  report: '报告',
  other: '其他',
}

function versionLabel(id: string | null) {
  if (!id) return '项目级'
  const version = versions.value.find((item) => item.id === id)
  if (!version) return id.slice(0, 8)
  const candidate = candidates.value.find((item) => item.id === version.candidate_id)
  return candidate
    ? `${candidate.antibody_category || '待分类'} · ${candidate.candidate_code} · ${version.version_code}`
    : version.version_code
}

async function load() {
  try {
    candidates.value = await fetchCandidates(props.projectId)
    versions.value = (
      await Promise.all(candidates.value.map((item) => fetchVersions(props.projectId, item.id)))
    ).flat()
    ;[artifacts.value, jobLinks.value] = await Promise.all([
      fetchArtifacts(props.projectId),
      fetchJobLinks(props.projectId),
    ])
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '资料加载失败')
  }
}

function onFileChange(event: Event) {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] || null
}

async function submitUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  saving.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    form.append('category', uploadForm.category)
    if (uploadForm.version_id) form.append('version_id', uploadForm.version_id)
    await uploadArtifact(props.projectId, form)
    showUpload.value = false
    selectedFile.value = null
    await load()
    ElMessage.success('附件已上传')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '上传失败')
  } finally {
    saving.value = false
  }
}

async function submitJobLink() {
  saving.value = true
  try {
    await createJobLink(props.projectId, {
      version_id: jobForm.version_id,
      job_id: jobForm.job_id.trim(),
      purpose: jobForm.purpose.trim() || undefined,
    })
    showJob.value = false
    jobForm.job_id = ''
    await load()
    ElMessage.success('计算任务已关联')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '关联失败')
  } finally {
    saving.value = false
  }
}

function openJobDialog() {
  jobForm.version_id = versions.value.at(-1)?.id || ''
  showJob.value = true
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function downloadRow(row: unknown) {
  try {
    await downloadArtifact(props.projectId, row as ProjectArtifact)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '下载失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="resources-panel">
    <section class="page-card resource-card">
      <div class="section-head">
        <div><h2>项目附件</h2><p>序列、结构、实验原始数据和报告</p></div>
        <el-button type="primary" @click="showUpload = true">上传附件</el-button>
      </div>
      <el-table :data="artifacts" size="small">
        <el-table-column prop="file_name" label="文件" min-width="220" />
        <el-table-column label="分类" width="90">
          <template #default="{ row }">{{ categoryText[row.category] || row.category }}</template>
        </el-table-column>
        <el-table-column label="版本" width="90">
          <template #default="{ row }">{{ versionLabel(row.version_id) }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="校验值" min-width="140">
          <template #default="{ row }"><code>{{ row.sha256.slice(0, 12) }}…</code></template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button text type="primary" @click="downloadRow(row)">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="page-card resource-card">
      <div class="section-head">
        <div><h2>关联计算任务</h2><p>保存计算输入、参数和结果快照</p></div>
        <el-button @click="openJobDialog">关联已有 Job</el-button>
      </div>
      <el-table :data="jobLinks" size="small">
        <el-table-column label="版本" width="90">
          <template #default="{ row }">{{ versionLabel(row.version_id) }}</template>
        </el-table-column>
        <el-table-column prop="engine" label="计算模块" width="150" />
        <el-table-column prop="purpose" label="用途" min-width="160" />
        <el-table-column prop="original_job_id" label="Job ID" min-width="240" />
      </el-table>
    </section>

    <el-dialog v-model="showUpload" title="上传项目附件" width="520px">
      <el-form label-position="top">
        <el-form-item label="文件">
          <input type="file" @change="onFileChange" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="分类">
            <el-select v-model="uploadForm.category" style="width: 100%">
              <el-option v-for="(label, value) in categoryText" :key="value" :label="label" :value="value" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联版本（可选）">
            <el-select v-model="uploadForm.version_id" clearable style="width: 100%">
              <el-option v-for="item in versions" :key="item.id" :label="item.version_code" :value="item.id" />
            </el-select>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitUpload">上传</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showJob" title="关联已有计算任务" width="520px">
      <el-form label-position="top">
        <el-form-item label="序列版本">
          <el-select v-model="jobForm.version_id" style="width: 100%">
            <el-option v-for="item in versions" :key="item.id" :label="item.version_code" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Job ID"><el-input v-model="jobForm.job_id" /></el-form-item>
        <el-form-item label="用途"><el-input v-model="jobForm.purpose" placeholder="例如结构验证" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showJob = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitJobLink">关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.resources-panel { display: grid; gap: 1rem; }
.resource-card { padding: 1rem; }
code { font-family: ui-monospace, monospace; font-size: 0.76rem; }
input[type='file'] { width: 100%; padding: 0.6rem; border: 1px dashed var(--border); border-radius: 8px; }
</style>
