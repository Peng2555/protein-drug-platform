<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchJobs } from '@/api/jobs'
import { createRosettaEvalJob, uploadRosettaEvalJob } from '@/api/rosetta'
import type { Job, RosettaEvalJob } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const route = useRoute()
const moduleJobs = useModuleJobsStore()

const submitMode = ref<'fold_job' | 'upload'>('fold_job')
const wtFoldJobId = ref('')
const mutantFoldJobIds = ref<string[]>([])
const foldOptions = ref<Job[]>([])
const name = ref('')
const nstruct = ref(3)
const nJobs = ref(16)
const antibodyChains = ref('')
const antigenChains = ref('')
const wtFile = ref<File | null>(null)
const mutantFiles = ref<File[]>([])
const submitting = ref(false)

const mutantOptions = computed(() => foldOptions.value.filter((j) => j.id !== wtFoldJobId.value))

async function loadFoldOptions() {
  try {
    const data = await fetchJobs(200, true)
    foldOptions.value = data.items.filter(
      (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
    )
  } catch {
    foldOptions.value = []
  }
}

function onWtUpload(arg: { raw?: File }) {
  wtFile.value = arg.raw || null
}

function onMutantUpload(upload: { raw?: File }, fileList: Array<{ raw?: File }>) {
  mutantFiles.value = fileList.map((f) => f.raw).filter((f): f is File => Boolean(f))
  void upload
}

async function submit() {
  if (submitMode.value === 'fold_job') {
    if (!wtFoldJobId.value) {
      ElMessage.warning('请选择 WT 折叠任务')
      return
    }
    if (!mutantFoldJobIds.value.length) {
      ElMessage.warning('请至少选择一个突变体折叠任务')
      return
    }
  } else if (!wtFile.value || mutantFiles.value.length === 0) {
    ElMessage.warning('请上传 WT 与至少一个突变体结构')
    return
  }
  submitting.value = true
  try {
    const body = {
      name: name.value.trim() || null,
      nstruct: nstruct.value,
      n_jobs: nJobs.value,
      antibody_chains: antibodyChains.value.trim(),
      antigen_chains: antigenChains.value.trim(),
      wt_fold_job_id: submitMode.value === 'fold_job' ? wtFoldJobId.value : null,
      mutant_fold_job_ids: submitMode.value === 'fold_job' ? mutantFoldJobIds.value : [],
    }
    let job: RosettaEvalJob
    if (submitMode.value === 'upload' && wtFile.value) {
      job = await uploadRosettaEvalJob(wtFile.value, mutantFiles.value, body)
    } else {
      job = await createRosettaEvalJob(body)
    }
    await moduleJobs.refreshRosetta()
    router.push({ name: 'rosetta-task', params: { id: job.id } })
    ElMessage.success('结构评价任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const wt = route.query.wt || route.query.fold_job
  if (typeof wt === 'string' && wt) {
    submitMode.value = 'fold_job'
    wtFoldJobId.value = wt
  }
  await loadFoldOptions()
})
</script>

<template>
  <div class="rosetta-new page-card">
    <header class="rosetta-new__head">
      <h1>新建结构评价</h1>
      <p>
        对 Boltz2 / ESMFold 预测的抗体–抗原复合物做 Rosetta FastRelax 与 InterfaceAnalyzer，相对 WT 计算 ΔΔG
        并综合排序。需本机已安装 Rosetta。
      </p>
    </header>
    <el-form label-position="top">
      <el-form-item label="结构来源">
        <el-radio-group v-model="submitMode">
          <el-radio value="fold_job">折叠任务</el-radio>
          <el-radio value="upload">上传 PDB / CIF</el-radio>
        </el-radio-group>
      </el-form-item>
      <template v-if="submitMode === 'fold_job'">
        <el-form-item label="WT 复合物">
          <el-select v-model="wtFoldJobId" placeholder="选择野生型折叠任务" filterable style="width: 100%">
            <el-option
              v-for="j in foldOptions"
              :key="j.id"
              :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
              :value="j.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="突变体复合物（可多选）">
          <el-select
            v-model="mutantFoldJobIds"
            multiple
            filterable
            placeholder="选择突变体折叠任务"
            style="width: 100%"
          >
            <el-option
              v-for="j in mutantOptions"
              :key="j.id"
              :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
              :value="j.id"
            />
          </el-select>
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="WT 结构">
          <el-upload :auto-upload="false" :limit="1" accept=".cif,.pdb,.mmcif" @change="onWtUpload">
            <el-button>选择 WT</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="突变体结构（可多选）">
          <el-upload :auto-upload="false" multiple accept=".cif,.pdb,.mmcif" @change="onMutantUpload">
            <el-button>选择突变体</el-button>
          </el-upload>
        </el-form-item>
      </template>
      <el-form-item label="任务名称（可选）">
        <el-input v-model="name" placeholder="例如：VHH 突变界面评价" maxlength="128" />
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="FastRelax nstruct">
            <el-input-number v-model="nstruct" :min="1" :max="10" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="并行核数 n_jobs">
            <el-input-number v-model="nJobs" :min="1" :max="64" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="抗体链（空=自动）">
            <el-input v-model="antibodyChains" placeholder="例如 H 或 H L" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="抗原链（空=自动）">
        <el-input v-model="antigenChains" placeholder="例如 A" style="max-width: 240px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">提交评价</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.rosetta-new {
  max-width: 760px;
}
.rosetta-new__head {
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
