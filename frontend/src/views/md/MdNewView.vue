<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import { createMdJob, uploadMdStructure } from '@/api/md'
import type { Job, MdJob } from '@/api/types'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const route = useRoute()
const foldStore = useFoldTasksStore()
const moduleJobs = useModuleJobsStore()

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

async function loadParentOptions() {
  const data = await fetchJobs(100, true)
  parentOptions.value = data.items.filter(
    (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
  )
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
    await Promise.all([moduleJobs.refreshMd(), foldStore.refreshMdTasks()])
    foldStore.startPolling()
    router.push({ name: 'md-task', params: { id: job.id } })
    ElMessage.success('MD 任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const parent = route.query.parent
  if (typeof parent === 'string') parentJobId.value = parent
  await loadParentOptions()
})
</script>

<template>
  <div class="md-new page-card">
    <header class="md-new__head">
      <h1>新建 MD 验证</h1>
      <p>从已完成折叠任务或上传 CIF/PDB 结构发起 GROMACS 显式溶剂模拟。</p>
    </header>
    <el-form label-position="top" size="default">
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
          <el-button>选择文件</el-button>
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
      <el-button type="primary" :loading="submitting" @click="submitMd">提交 MD</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.md-new {
  padding: 1.15rem 1.25rem 1.4rem;
}

.md-new__head {
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
}
</style>
