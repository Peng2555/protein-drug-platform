<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import {
  createMaturationJob,
  deleteMaturationJob,
  fetchMaturationJobs,
  uploadMaturationJob,
} from '@/api/maturation'
import type { Job, MaturationJob } from '@/api/types'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { MATURATION_STAGE_LABELS, statusLabel } from '@/utils/constants'

const router = useRouter()
const route = useRoute()
const foldStore = useFoldTasksStore()

const structureSource = ref<'upload' | 'boltz2' | 'esmfold2' | 'fold_job'>('upload')
const parentJobId = ref('')
const parentOptions = ref<Job[]>([])

const jobName = ref('')
const fastaInput = ref('')
const uploadFile = ref<File | null>(null)
const binderChainId = ref('H')
const antigenChainId = ref('A')
const cdrMask = ref<string[]>(['CDR-H3'])

const numSamples = ref(100)
const steps = ref(10)
const maxAntigenSize = ref(384)
const temperature = ref(1.0)
const chunkSize = ref(64)
const relax = ref(false)
const gpuCount = ref(2)
const useMsaServer = ref(true)

const maturationJobs = ref<MaturationJob[]>([])
const submitting = ref(false)

const activeId = computed(() =>
  route.name === 'maturation-job' ? (route.params.id as string) : null,
)

const cdrOptions = ['CDR-H1', 'CDR-H2', 'CDR-H3', 'CDR-L1', 'CDR-L2', 'CDR-L3']

async function loadParentOptions() {
  const data = await fetchJobs(100, true)
  parentOptions.value = data.items.filter(
    (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
  )
}

async function loadList() {
  try {
    const data = await fetchMaturationJobs(50)
    maturationJobs.value = data.items ?? []
    foldStore.maturationJobs = data.items ?? []
  } catch {
    maturationJobs.value = []
  }
}

function onUploadChange(uploadFileArg: { raw?: File }) {
  uploadFile.value = uploadFileArg.raw || null
}

async function submit() {
  const fasta = fastaInput.value.trim()
  if (!fasta) {
    ElMessage.warning('请填写 Parent FASTA（重链 + 抗原）')
    return
  }
  if (structureSource.value === 'upload' && !uploadFile.value) {
    ElMessage.warning('请上传复合物结构文件')
    return
  }
  if (structureSource.value === 'fold_job' && !parentJobId.value) {
    ElMessage.warning('请选择已有折叠任务')
    return
  }

  submitting.value = true
  try {
    const iggm = {
      num_samples: numSamples.value,
      steps: steps.value,
      max_antigen_size: maxAntigenSize.value,
      temperature: temperature.value,
      chunk_size: chunkSize.value,
      relax: relax.value,
      gpu_count: gpuCount.value,
    }
    let job: MaturationJob
    if (structureSource.value === 'upload') {
      job = await uploadMaturationJob(fasta, uploadFile.value!, {
        name: jobName.value.trim() || null,
        binder_chain_id: binderChainId.value,
        antigen_chain_id: antigenChainId.value,
        cdr_mask: cdrMask.value.join(','),
        ...iggm,
      })
    } else {
      job = await createMaturationJob({
        fasta,
        name: jobName.value.trim() || null,
        structure_source: structureSource.value,
        fold_job_id: structureSource.value === 'fold_job' ? parentJobId.value : null,
        binder_chain_id: binderChainId.value,
        antigen_chain_id: antigenChainId.value,
        cdr_mask: cdrMask.value,
        use_msa_server: useMsaServer.value,
        iggm,
      })
    }
    jobName.value = ''
    fastaInput.value = ''
    uploadFile.value = null
    await loadList()
    foldStore.startPolling()
    router.push({ name: 'maturation-job', params: { id: job.id } })
    ElMessage.success('亲和力成熟任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

function openJob(job: MaturationJob) {
  router.push({ name: 'maturation-job', params: { id: job.id } })
}

async function onDelete(job: MaturationJob) {
  const label = job.name || job.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(`确定删除任务「${label}」吗？`, '删除任务', { type: 'warning' })
    await deleteMaturationJob(job.id)
    if (activeId.value === job.id) router.push({ name: 'maturation' })
    await loadList()
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
  try {
    await Promise.all([loadParentOptions(), loadList()])
    foldStore.startPolling()
  } catch {
    /* sidebar still usable if list APIs fail */
  }
})
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>亲和力成熟 (IgGM)</h3>
      <el-form label-position="top" size="small">
        <el-form-item label="任务名称（可选）">
          <el-input v-model="jobName" />
        </el-form-item>

        <el-form-item label="Parent FASTA">
          <el-input
            v-model="fastaInput"
            type="textarea"
            :rows="6"
            placeholder=">H&#10;EVQLV...&#10;>A&#10;QVQVV..."
          />
        </el-form-item>

        <div class="inline-fields">
          <el-form-item label="重链 ID">
            <el-input v-model="binderChainId" style="width: 70px" />
          </el-form-item>
          <el-form-item label="抗原 ID">
            <el-input v-model="antigenChainId" style="width: 70px" />
          </el-form-item>
        </div>

        <el-form-item label="成熟 CDR 区域">
          <el-checkbox-group v-model="cdrMask">
            <el-checkbox v-for="c in cdrOptions" :key="c" :label="c" />
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="复合物结构来源">
          <el-radio-group v-model="structureSource" class="source-radio">
            <el-radio value="upload">上传 PDB/CIF</el-radio>
            <el-radio value="boltz2">Boltz2 预测</el-radio>
            <el-radio value="esmfold2">ESMFold2 预测</el-radio>
            <el-radio value="fold_job">已有折叠任务</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="structureSource === 'upload'" label="结构文件">
          <el-upload
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            accept=".cif,.pdb,.mmcif"
            @change="onUploadChange"
          >
            <el-button size="small">选择文件</el-button>
          </el-upload>
        </el-form-item>

        <el-form-item v-if="structureSource === 'fold_job'" label="折叠任务">
          <el-select v-model="parentJobId" placeholder="选择已完成任务" filterable style="width: 100%">
            <el-option
              v-for="j in parentOptions"
              :key="j.id"
              :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
              :value="j.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="structureSource === 'boltz2'" label="MSA">
          <el-switch v-model="useMsaServer" active-text="ColabFold MSA" />
        </el-form-item>

        <el-divider content-position="left">IgGM 参数</el-divider>

        <div class="inline-fields">
          <el-form-item label="采样数/位点">
            <el-input-number v-model="numSamples" :min="1" :max="500" />
          </el-form-item>
          <el-form-item label="扩散步数">
            <el-input-number v-model="steps" :min="1" :max="50" />
          </el-form-item>
        </div>
        <div class="inline-fields">
          <el-form-item label="GPU 数">
            <el-input-number v-model="gpuCount" :min="1" :max="8" />
          </el-form-item>
          <el-form-item label="抗原截断">
            <el-input-number v-model="maxAntigenSize" :min="50" :max="2000" :step="50" />
          </el-form-item>
        </div>
        <div class="inline-fields">
          <el-form-item label="温度">
            <el-input-number v-model="temperature" :min="0.1" :max="2" :step="0.1" />
          </el-form-item>
          <el-form-item label="Chunk">
            <el-input-number v-model="chunkSize" :min="8" :max="256" :step="8" />
          </el-form-item>
        </div>
        <el-form-item label="PyRosetta relax">
          <el-switch v-model="relax" />
        </el-form-item>

        <el-button type="primary" size="small" :loading="submitting" @click="submit">
          提交成熟任务
        </el-button>
      </el-form>

      <div class="task-list-section">
        <div class="task-list-head">
          <h3>成熟任务</h3>
          <el-button size="small" text @click="loadList">刷新</el-button>
        </div>
        <div v-if="!maturationJobs.length" class="empty-state">暂无任务</div>
        <div v-else class="task-list">
          <div
            v-for="j in maturationJobs"
            :key="j.id"
            class="job-item task-item"
            :class="{ active: activeId === j.id }"
            @click="openJob(j)"
          >
            <div class="job-item-top">
              <div class="title">
                <span class="task-kind-badge kind-mat">IgGM</span>
                {{ j.name || j.id.slice(0, 8) }}
              </div>
              <div class="job-item-actions" @click.stop>
                <el-tag :type="statusTagType(j.status)" size="small">
                  {{ statusLabel(j.status) }}
                </el-tag>
                <button type="button" class="job-delete-btn" @click="onDelete(j)">×</button>
              </div>
            </div>
            <div class="meta">
              亲和力成熟
              <template v-if="j.stage">
                · {{ MATURATION_STAGE_LABELS[j.stage] || j.stage }}
              </template>
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

.kind-mat {
  background: #fce7f3;
  color: #be185d;
}

.inline-fields {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.source-radio {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

h3 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  color: var(--title);
}
</style>
