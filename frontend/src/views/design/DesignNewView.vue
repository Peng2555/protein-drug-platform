<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import { createDesignJob, uploadDesignJob } from '@/api/design'
import type { DesignJob, Job } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const route = useRoute()
const moduleJobs = useModuleJobsStore()

const submitMode = ref<'fold_job' | 'upload'>('fold_job')
const foldJobId = ref('')
const foldOptions = ref<Job[]>([])
const name = ref('')
const designedChains = ref('')
const numSeq = ref(8)
const samplingTemp = ref(0.1)
const seed = ref(0)
const backboneNoise = ref(0)
const omitAas = ref('X')
const uploadFile = ref<File | null>(null)
const submitting = ref(false)

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

async function submit() {
  if (submitMode.value === 'fold_job' && !foldJobId.value) {
    ElMessage.warning('请选择已完成的折叠任务')
    return
  }
  if (submitMode.value === 'upload' && !uploadFile.value) {
    ElMessage.warning('请上传 PDB/CIF 结构文件')
    return
  }
  submitting.value = true
  try {
    const body = {
      name: name.value.trim() || null,
      designed_chains: designedChains.value.trim(),
      num_seq_per_target: numSeq.value,
      sampling_temp: samplingTemp.value,
      seed: seed.value,
      backbone_noise: backboneNoise.value,
      omit_aas: omitAas.value || 'X',
      fold_job_id: submitMode.value === 'fold_job' ? foldJobId.value : null,
    }
    let job: DesignJob
    if (submitMode.value === 'upload' && uploadFile.value) {
      job = await uploadDesignJob(uploadFile.value, body)
    } else {
      job = await createDesignJob(body)
    }
    await moduleJobs.refreshDesign()
    router.push({ name: 'design-task', params: { id: job.id } })
    ElMessage.success('序列设计任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const fold = route.query.fold_job
  if (typeof fold === 'string' && fold) {
    submitMode.value = 'fold_job'
    foldJobId.value = fold
  }
  await loadFoldOptions()
})
</script>

<template>
  <div class="design-new page-card">
    <header class="design-new__head">
      <h1>新建序列设计</h1>
      <p>基于 ProteinMPNN，从折叠任务或上传骨架结构生成设计序列。</p>
    </header>
    <el-form label-position="top" size="default">
      <el-form-item label="结构来源">
        <el-radio-group v-model="submitMode">
          <el-radio value="fold_job">折叠任务</el-radio>
          <el-radio value="upload">上传结构</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="submitMode === 'fold_job'" label="折叠任务">
        <el-select v-model="foldJobId" placeholder="选择已完成任务" filterable style="width: 100%">
          <el-option
            v-for="j in foldOptions"
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
          accept=".cif,.pdb,.mmcif"
          @change="onUploadChange"
        >
          <el-button>选择文件</el-button>
        </el-upload>
      </el-form-item>
      <el-form-item label="任务名称（可选）">
        <el-input v-model="name" placeholder="例如：H 链重设计" maxlength="128" />
      </el-form-item>
      <el-form-item label="设计链（空=全部）">
        <el-input v-model="designedChains" placeholder="例如：H 或 H A" />
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="每靶点序列数">
            <el-input-number v-model="numSeq" :min="1" :max="64" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="采样温度">
            <el-input-number
              v-model="samplingTemp"
              :min="0.05"
              :max="1"
              :step="0.05"
              :precision="2"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="随机种子">
            <el-input-number v-model="seed" :min="0" :max="999999" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="骨架噪声">
            <el-input-number
              v-model="backboneNoise"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="排除氨基酸">
            <el-input v-model="omitAas" placeholder="默认 X" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">提交设计</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.design-new {
  max-width: 720px;
}
.design-new__head {
  margin-bottom: 1.25rem;
  h1 {
    margin: 0 0 0.35rem;
    font-size: 1.35rem;
  }
  p {
    margin: 0;
    color: var(--muted);
    font-size: 0.9rem;
  }
}
</style>
