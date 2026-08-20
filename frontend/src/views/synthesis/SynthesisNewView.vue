<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { runSynthesisJob } from '@/api/synthesis'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const jobName = ref('')
const shmFile = ref<File | null>(null)
const iggmFile = ref<File | null>(null)
const originFile = ref<File | null>(null)
const minSeqCount = ref(30)
const minExtraCount = ref(100)
const vGene = ref('')
const chainId = ref('H')
const submitting = ref(false)

function onShmChange(f: { raw?: File }) {
  shmFile.value = f.raw ?? null
}

function onIggmChange(f: { raw?: File }) {
  iggmFile.value = f.raw ?? null
}

function onOriginChange(f: { raw?: File }) {
  originFile.value = f.raw ?? null
}

async function submit() {
  if (!shmFile.value) {
    ElMessage.warning('请上传 SHM 测序大表')
    return
  }
  if (!iggmFile.value) {
    ElMessage.warning('请上传 IgGM CDR3 突变表 (cdr3_all_1to3.csv)')
    return
  }
  submitting.value = true
  try {
    const result = await runSynthesisJob(shmFile.value, iggmFile.value, {
      name: jobName.value.trim() || null,
      originFasta: originFile.value,
      min_seq_count: minSeqCount.value,
      min_extra_count: minExtraCount.value,
      chain_id: chainId.value,
      v_gene: vGene.value.trim() || undefined,
    })
    jobName.value = ''
    shmFile.value = null
    iggmFile.value = null
    originFile.value = null
    await moduleJobs.refreshSynthesis()
    router.push({ name: 'synthesis-task', params: { id: result.job_id! } })
    ElMessage.success(
      `筛选完成：匹配 ${result.matched_count} 行，送合成 ${result.order_count} 条（A ${result.a_count} / B ${result.b_count}）`,
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '筛选失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="synthesis-new page-card">
    <header class="synthesis-new__head">
      <h1>新建合成候选筛选</h1>
      <p>上传 SHM 测序大表与 IgGM 突变表，交叉比对后输出送合成清单（A/B 档）。</p>
    </header>
    <el-form label-position="top" size="default">
      <el-form-item label="任务名称（可选）">
        <el-input v-model="jobName" placeholder="如 CD200R_round1" />
      </el-form-item>

      <el-form-item label="SHM 测序大表" required>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".csv,.tsv,.xlsx,.xls"
          :on-change="onShmChange"
          :on-remove="() => (shmFile = null)"
        >
          <el-button>选择 SHM 大表</el-button>
        </el-upload>
        <p class="field-hint">需含 kabat_FR1…kabat_FR4 与 kabat_CDR3 列</p>
      </el-form-item>

      <el-form-item label="IgGM CDR3 突变表" required>
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".csv,.tsv,.xlsx,.xls"
          :on-change="onIggmChange"
          :on-remove="() => (iggmFile = null)"
        >
          <el-button>选择 cdr3_all_1to3.csv</el-button>
        </el-upload>
      </el-form-item>

      <el-form-item label="母本 origin.fasta（可选）">
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".fasta,.fa,.faa"
          :on-change="onOriginChange"
          :on-remove="() => (originFile = null)"
        >
          <el-button>选择 origin.fasta</el-button>
        </el-upload>
        <p class="field-hint">用于在 SHM 表中定位母本参考行；不上传则取最高 count 行</p>
      </el-form-item>

      <el-divider content-position="left">筛选参数</el-divider>

      <div class="inline-fields">
        <el-form-item label="重链 ID">
          <el-input v-model="chainId" style="width: 70px" />
        </el-form-item>
        <el-form-item label="v_gene（可选）">
          <el-input v-model="vGene" placeholder="自动识别" />
        </el-form-item>
      </div>
      <div class="inline-fields">
        <el-form-item label="SHM 最低 count">
          <el-input-number v-model="minSeqCount" :min="0" :max="999999" />
        </el-form-item>
        <el-form-item label="B档最低 count">
          <el-input-number v-model="minExtraCount" :min="0" :max="999999" />
        </el-form-item>
      </div>

      <el-button type="primary" :loading="submitting" @click="submit">运行筛选</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.synthesis-new {
  padding: 1.15rem 1.25rem 1.4rem;
}

.synthesis-new__head {
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

.field-hint {
  margin: 0.35rem 0 0;
  font-size: 0.75rem;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
</style>
