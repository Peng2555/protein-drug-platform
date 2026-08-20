<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import {
  createMaturationJob,
  uploadMaturationJob,
} from '@/api/maturation'
import type { Job, MaturationJob } from '@/api/types'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const foldStore = useFoldTasksStore()
const moduleJobs = useModuleJobsStore()

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

const submitting = ref(false)

const needsFasta = computed(
  () => structureSource.value === 'boltz2' || structureSource.value === 'esmfold2',
)

const fastaHint = computed(() => {
  if (structureSource.value === 'fold_job') {
    return '可选：留空则从所选折叠任务自动读取序列'
  }
  if (structureSource.value === 'upload') {
    return '可选：留空则从上传的结构文件按链 ID 自动提取'
  }
  return 'Boltz2/ESMFold2 预测结构前必须提供序列'
})

const cdrOptions = ['CDR-H1', 'CDR-H2', 'CDR-H3', 'CDR-L1', 'CDR-L2', 'CDR-L3']

async function loadParentOptions() {
  const data = await fetchJobs(100, true)
  parentOptions.value = data.items.filter(
    (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
  )
}

function onUploadChange(uploadFileArg: { raw?: File }) {
  uploadFile.value = uploadFileArg.raw || null
}

watch(parentJobId, (id) => {
  if (!id || structureSource.value !== 'fold_job') return
  const parent = parentOptions.value.find((j) => j.id === id)
  if (!parent?.chains_json) return
  const keys = Object.keys(parent.chains_json)
  if (keys.length >= 2) {
    binderChainId.value = keys[0]
    antigenChainId.value = keys[1]
  }
})

async function submit() {
  const fasta = fastaInput.value.trim()
  if (needsFasta.value && !fasta) {
    ElMessage.warning('Boltz2/ESMFold2 预测结构需要填写 Parent FASTA')
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
      job = await uploadMaturationJob(uploadFile.value!, {
        fasta: fasta || null,
        name: jobName.value.trim() || null,
        binder_chain_id: binderChainId.value,
        antigen_chain_id: antigenChainId.value,
        cdr_mask: cdrMask.value.join(','),
        ...iggm,
      })
    } else {
      job = await createMaturationJob({
        fasta: fasta || null,
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
    await Promise.all([moduleJobs.refreshMaturation(), foldStore.refreshMaturationTasks()])
    foldStore.startPolling()
    router.push({ name: 'maturation-task', params: { id: job.id } })
    ElMessage.success('亲和力成熟任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  void loadParentOptions()
})
</script>

<template>
  <div class="maturation-new page-card">
    <header class="maturation-new__head">
      <h1>新建亲和力成熟</h1>
      <p>用 IgGM 在指定 CDR 上采样变体。可上传 PDB/CIF、预测结构，或直接选用已有折叠任务作为复合物输入。</p>
    </header>
    <el-form label-position="top" size="default">
      <el-form-item label="任务名称（可选）">
        <el-input v-model="jobName" />
      </el-form-item>

      <el-form-item :label="needsFasta ? 'Parent FASTA（必填）' : 'Parent FASTA（可选）'">
        <el-input
          v-model="fastaInput"
          type="textarea"
          :rows="6"
          :placeholder="needsFasta ? '>H\nEVQLV...\n>A\nQVQVV...' : '留空则从结构自动提取序列'"
        />
        <p class="field-hint">{{ fastaHint }}</p>
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
          <el-button>选择文件</el-button>
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
        <el-form-item label="每位点采样数">
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
      <p class="field-hint">
        总推理次数 ≈ 每位点采样数 × CDR 掩码氨基酸位数（如 100×12≈1200）。多 GPU 并行完成同一批任务。
      </p>

      <el-button type="primary" :loading="submitting" @click="submit">提交成熟任务</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.maturation-new {
  padding: 1.15rem 1.25rem 1.4rem;
}

.maturation-new__head {
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

.field-hint {
  margin: 0.35rem 0 0;
  font-size: 0.75rem;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
</style>
