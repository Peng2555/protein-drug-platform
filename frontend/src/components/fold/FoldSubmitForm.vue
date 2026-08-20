<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createJob } from '@/api/jobs'
import { createVhhPanel } from '@/api/batches'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { EXAMPLE_FASTA } from '@/utils/constants'
import { importHeavyChainFile, parseHeavyChainText, type HeavyChainRow } from '@/utils/heavyChain'

const router = useRouter()
const store = useFoldTasksStore()

const submitTab = ref<'single' | 'batch'>('single')
const fastaTab = ref<'paste' | 'file'>('paste')
const heavyTab = ref<'csv' | 'fasta'>('csv')

const jobName = ref('')
const fastaInput = ref('')
const fastaFile = ref<File | null>(null)

const batchName = ref('')
const targetName = ref('')
const targetSeq = ref('')
const targetChainId = ref('A')
const heavyChainId = ref('H')
const heavyCsvInput = ref('')
const heavyFastaInput = ref('')
const heavyFileHint = ref('')

const foldEngine = ref<'boltz2' | 'esmfold2'>('boltz2')
const esmLoops = ref(3)
const esmSteps = ref(200)
const esmSamples = ref(1)

const submitting = ref(false)
const lastStatus = ref('')

const heavyPreview = computed(() => {
  const text = heavyTab.value === 'fasta' ? heavyFastaInput.value : heavyCsvInput.value
  return parseHeavyChainText(text).rows
})

function getHeavyChains(): HeavyChainRow[] {
  const text = heavyTab.value === 'fasta' ? heavyFastaInput.value : heavyCsvInput.value
  return parseHeavyChainText(text).rows
}

function getFastaForSubmit() {
  if (fastaTab.value === 'file' && fastaFile.value) {
    return fastaFile.value.text()
  }
  return Promise.resolve(fastaInput.value.trim())
}

async function onFastaFileChange(file: File | null) {
  fastaFile.value = file
  if (file) {
    fastaInput.value = await file.text()
  }
}

async function onHeavyFileChange(uploadFile: { raw?: File } | File) {
  const file = uploadFile instanceof File ? uploadFile : uploadFile.raw
  if (!file) return
  try {
    const data = await importHeavyChainFile(file)
    if (data.format === 'fasta') {
      heavyFastaInput.value = data.text
      heavyCsvInput.value = ''
      heavyTab.value = 'fasta'
    } else {
      heavyCsvInput.value = data.text
      heavyFastaInput.value = ''
      heavyTab.value = 'csv'
    }
    heavyFileHint.value = data.row_count
      ? `已导入 ${file.name}（${data.encoding}）· 识别 ${data.row_count} 条重链`
      : `已读取 ${file.name}，但未解析到有效重链`
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入失败')
  }
}

function loadExample() {
  fastaTab.value = 'paste'
  fastaInput.value = EXAMPLE_FASTA
  jobName.value = 'vhh_lysozyme_demo'
}

async function submitSingle() {
  const fasta = await getFastaForSubmit()
  if (!fasta) {
    ElMessage.warning(fastaTab.value === 'file' ? '请上传 FASTA 文件' : '请粘贴 FASTA 序列')
    return
  }
  submitting.value = true
  lastStatus.value = '正在提交单条预测…'
  try {
    const engine = foldEngine.value
    const job = await createJob({
      fasta,
      name: jobName.value.trim() || null,
      engine,
      use_msa_server: engine === 'boltz2',
      ...(engine === 'esmfold2'
        ? {
            esmfold_params: {
              num_loops: esmLoops.value,
              num_sampling_steps: esmSteps.value,
              num_diffusion_samples: esmSamples.value,
            },
          }
        : {}),
    })
    jobName.value = ''
    fastaInput.value = ''
    fastaFile.value = null
    await store.refreshFoldTasks()
    store.startPolling()
    lastStatus.value = `已提交「${job.name || job.id.slice(0, 8)}」，状态：${job.status}`
    ElMessage.success('任务已提交')
    router.push({ name: 'fold-task', params: { id: job.id } })
  } catch (e) {
    lastStatus.value = e instanceof Error ? e.message : '提交失败'
    ElMessage.error(lastStatus.value)
  } finally {
    submitting.value = false
  }
}

async function submitBatch() {
  const chains = getHeavyChains()
  if (!targetName.value.trim()) {
    ElMessage.warning('请填写靶点名称')
    return
  }
  if (!targetSeq.value.trim()) {
    ElMessage.warning('请填写抗原序列')
    return
  }
  if (!chains.length) {
    ElMessage.warning('请提供至少一条重链（CSV 或 FASTA）')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认提交批量预测？\n\n靶点：${targetName.value}\n重链数：${chains.length}\n\n任务将依次排队运行。`,
      '批量预测',
      { type: 'info' },
    )
  } catch {
    return
  }

  submitting.value = true
  lastStatus.value = '正在提交批量预测…'
  try {
    const engine = foldEngine.value
    const data = await createVhhPanel({
      batch_name: batchName.value.trim() || null,
      target: {
        name: targetName.value.trim(),
        chain_id: targetChainId.value.trim() || 'A',
        sequence: targetSeq.value.replace(/\s/g, ''),
      },
      heavy_chain_id: heavyChainId.value.trim() || 'H',
      heavy_chains: chains,
      engine,
      use_msa_server: engine === 'boltz2',
      ...(engine === 'esmfold2'
        ? {
            esmfold_params: {
              num_loops: esmLoops.value,
              num_sampling_steps: esmSteps.value,
              num_diffusion_samples: esmSamples.value,
            },
          }
        : {}),
    })
    let note = `已创建批次「${data.batch.name}」，共 ${data.job_ids.length} 个任务。`
    if (data.skipped_duplicates) note += `（跳过 ${data.skipped_duplicates} 条重复序列）`
    lastStatus.value = note
    ElMessage.success(note)
    heavyCsvInput.value = ''
    heavyFastaInput.value = ''
    heavyFileHint.value = ''
    await store.refreshFoldTasks()
    store.startPolling()
    router.push({ name: 'fold-batch', params: { id: data.batch.id } })
  } catch (e) {
    if (e !== 'cancel') {
      lastStatus.value = e instanceof Error ? e.message : '提交失败'
      ElMessage.error(lastStatus.value)
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="fold-submit">
    <div class="fold-submit__tabs">
      <button
        type="button"
        class="fold-submit__tab"
        :class="{ active: submitTab === 'single' }"
        @click="submitTab = 'single'"
      >
        单条预测
      </button>
      <button
        type="button"
        class="fold-submit__tab"
        :class="{ active: submitTab === 'batch' }"
        @click="submitTab = 'batch'"
      >
        VHH 批量
      </button>
    </div>

    <div v-show="submitTab === 'single'" class="fold-submit__panel">
      <el-form label-position="top">
        <el-form-item label="任务名称（可选）">
          <el-input v-model="jobName" placeholder="例如 vhh_demo" />
        </el-form-item>
        <el-form-item label="预测引擎">
          <el-radio-group v-model="foldEngine">
            <el-radio value="boltz2">Boltz2</el-radio>
            <el-radio value="esmfold2">ESMFold2</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="foldEngine === 'esmfold2'">
          <el-collapse class="params-collapse">
            <el-collapse-item title="ESMFold2 参数" name="esm">
              <el-form-item label="loops">
                <el-input-number v-model="esmLoops" :min="1" :max="8" />
              </el-form-item>
              <el-form-item label="sampling steps">
                <el-input-number v-model="esmSteps" :min="50" :max="500" :step="50" />
              </el-form-item>
              <el-form-item label="diffusion samples">
                <el-input-number v-model="esmSamples" :min="1" :max="5" />
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
        </template>
        <el-form-item label="FASTA 序列">
          <el-radio-group v-model="fastaTab" class="mini-tabs">
            <el-radio-button value="paste">粘贴</el-radio-button>
            <el-radio-button value="file">上传</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="fastaTab === 'paste'"
            v-model="fastaInput"
            type="textarea"
            :rows="10"
            placeholder=">H&#10;DVQLV...&#10;>A&#10;KVFGR..."
            class="mt-sm"
          />
          <el-upload
            v-else
            class="mt-sm"
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept=".fa,.fasta,.txt"
            @change="(f: { raw?: File }) => onFastaFileChange(f.raw || null)"
          >
            <div class="el-upload__text">拖放 FASTA 或点击上传</div>
          </el-upload>
          <p v-if="foldEngine === 'boltz2'" class="form-hint">
            Boltz2 要求 FASTA 链 ID 不超过 4 个字符（如 &gt;A、&gt;H），勿使用 antigen、parent 等长名称。
          </p>
        </el-form-item>
        <div class="form-actions">
          <el-button @click="loadExample">加载示例</el-button>
          <el-button type="primary" :loading="submitting" @click="submitSingle">
            开始预测
          </el-button>
        </div>
      </el-form>
    </div>

    <div v-show="submitTab === 'batch'" class="fold-submit__panel">
      <el-form label-position="top">
        <el-form-item label="批次名称（可选）">
          <el-input v-model="batchName" />
        </el-form-item>
        <el-form-item label="靶点名称">
          <el-input v-model="targetName" />
        </el-form-item>
        <el-form-item label="抗原序列">
          <el-input v-model="targetSeq" type="textarea" :rows="4" />
        </el-form-item>
        <div class="inline-fields">
          <el-form-item label="抗原链 ID">
            <el-input v-model="targetChainId" style="width: 100px" />
          </el-form-item>
          <el-form-item label="重链链 ID">
            <el-input v-model="heavyChainId" style="width: 100px" />
          </el-form-item>
        </div>
        <el-form-item label="预测引擎">
          <el-radio-group v-model="foldEngine">
            <el-radio value="boltz2">Boltz2</el-radio>
            <el-radio value="esmfold2">ESMFold2</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="重链列表">
          <el-radio-group v-model="heavyTab" class="mini-tabs">
            <el-radio-button value="csv">CSV</el-radio-button>
            <el-radio-button value="fasta">FASTA</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="heavyTab === 'csv'"
            v-model="heavyCsvInput"
            type="textarea"
            :rows="6"
            placeholder="vhh_id,sequence"
            class="mt-sm"
          />
          <el-input
            v-else
            v-model="heavyFastaInput"
            type="textarea"
            :rows="6"
            placeholder=">VHH_001&#10;QVQL..."
            class="mt-sm"
          />
          <el-upload
            class="mt-sm"
            :auto-upload="false"
            :show-file-list="false"
            accept=".csv,.txt,.fasta,.fa,.xlsx,.xlsm"
            @change="onHeavyFileChange"
          >
            <el-button>导入 CSV / Excel / FASTA</el-button>
          </el-upload>
          <p v-if="heavyFileHint" class="file-hint">{{ heavyFileHint }}</p>
          <p v-if="heavyPreview.length" class="file-hint">已识别 {{ heavyPreview.length }} 条重链</p>
        </el-form-item>
        <el-button type="primary" :loading="submitting" @click="submitBatch">
          开始批量预测
        </el-button>
      </el-form>
    </div>

    <p v-if="lastStatus" class="fold-submit__status">{{ lastStatus }}</p>
  </div>
</template>

<style scoped lang="scss">
.fold-submit {
  max-width: 720px;
}

.fold-submit__tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 1rem;
  padding: 0.25rem;
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

.fold-submit__tab {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 0.55rem 0.75rem;
  border-radius: 6px;
  font-size: 0.88rem;
  cursor: pointer;

  &.active {
    background: #fff;
    color: var(--bio-green-dark);
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(35, 35, 47, 0.06);
  }
}

.fold-submit__panel {
  padding: 0.15rem 0.1rem;
}

.mt-sm {
  margin-top: 0.5rem;
  width: 100%;
}

.inline-fields {
  display: flex;
  gap: 1rem;
}

.form-actions {
  display: flex;
  gap: 0.65rem;
  margin-top: 0.35rem;
}

.form-hint,
.file-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.params-collapse {
  margin-bottom: 0.75rem;
}

.fold-submit__status {
  margin: 1rem 0 0;
  padding: 0.65rem 0.8rem;
  border-radius: 8px;
  background: var(--bio-blue-light);
  border: 1px solid rgba(46, 90, 165, 0.14);
  color: var(--bio-blue-dark);
  font-size: 0.82rem;
}
</style>
