<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createJob, deleteJob } from '@/api/jobs'
import { createVhhPanel, deleteBatch } from '@/api/batches'
import { useFoldTasksStore } from '@/stores/foldTasks'
import type { Batch, Job } from '@/api/types'
import {
  EXAMPLE_FASTA,
  batchStatusLabel,
  engineLabel,
  statusLabel,
} from '@/utils/constants'
import { importHeavyChainFile, parseHeavyChainText, type HeavyChainRow } from '@/utils/heavyChain'

const router = useRouter()
const route = useRoute()
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

const activeJobId = computed(() =>
  route.name === 'fold-job' ? (route.params.id as string) : null,
)
const activeBatchId = computed(() =>
  route.name === 'fold-batch' ? (route.params.id as string) : null,
)

const heavyPreview = computed(() => {
  const text = heavyTab.value === 'fasta' ? heavyFastaInput.value : heavyCsvInput.value
  const parsed = parseHeavyChainText(text)
  return parsed.rows
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
  try {
    const engine = foldEngine.value
    await createJob({
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
    ElMessage.success('任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
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
    ElMessage.success(note)
    heavyCsvInput.value = ''
    heavyFastaInput.value = ''
    heavyFileHint.value = ''
    await store.refreshFoldTasks()
    store.startPolling()
    router.push({ name: 'fold-batch', params: { id: data.batch.id } })
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e instanceof Error ? e.message : '提交失败')
    }
  } finally {
    submitting.value = false
  }
}

function openJob(job: Job) {
  router.push({ name: 'fold-job', params: { id: job.id } })
}

function openBatch(batch: Batch) {
  router.push({ name: 'fold-batch', params: { id: batch.id } })
}

async function onDeleteJob(job: Job) {
  const label = job.name || job.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${label}」吗？\n\n将同时删除数据库记录和 outputs 目录中的结果文件，此操作不可恢复。`,
      '删除任务',
      { type: 'warning' },
    )
    await deleteJob(job.id)
    if (activeJobId.value === job.id) router.push({ name: 'fold' })
    await store.refreshFoldTasks()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function onDeleteBatch(batch: Batch) {
  try {
    await ElMessageBox.confirm(`确定删除批次「${batch.name}」吗？此操作不可恢复。`, '删除批次', {
      type: 'warning',
    })
    await deleteBatch(batch.id)
    if (activeBatchId.value === batch.id) router.push({ name: 'fold' })
    await store.refreshFoldTasks()
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
  if (status === 'running' || status === 'partial') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

onMounted(() => {
  void store.refreshFoldTasks()
  store.startPolling()
})
</script>

<template>
  <aside class="fold-sidebar page-card page-card--accent">
    <div class="fold-sidebar__tabs">
      <button
        type="button"
        class="sidebar-tab"
        :class="{ active: submitTab === 'single' }"
        @click="submitTab = 'single'"
      >
        单条预测
      </button>
      <button
        type="button"
        class="sidebar-tab"
        :class="{ active: submitTab === 'batch' }"
        @click="submitTab = 'batch'"
      >
        VHH 批量
      </button>
    </div>

    <div v-show="submitTab === 'single'" class="submit-panel">
      <el-form label-position="top" size="small">
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
          <el-form-item label="loops">
            <el-input-number v-model="esmLoops" :min="1" :max="8" />
          </el-form-item>
          <el-form-item label="sampling steps">
            <el-input-number v-model="esmSteps" :min="50" :max="500" :step="50" />
          </el-form-item>
          <el-form-item label="diffusion samples">
            <el-input-number v-model="esmSamples" :min="1" :max="5" />
          </el-form-item>
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
            :rows="6"
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
        </el-form-item>
        <div class="form-actions">
          <el-button size="small" @click="loadExample">加载示例</el-button>
          <el-button type="primary" size="small" :loading="submitting" @click="submitSingle">
            提交预测
          </el-button>
        </div>
      </el-form>
    </div>

    <div v-show="submitTab === 'batch'" class="submit-panel">
      <el-form label-position="top" size="small">
        <el-form-item label="批次名称（可选）">
          <el-input v-model="batchName" />
        </el-form-item>
        <el-form-item label="靶点名称">
          <el-input v-model="targetName" />
        </el-form-item>
        <el-form-item label="抗原序列">
          <el-input v-model="targetSeq" type="textarea" :rows="3" />
        </el-form-item>
        <div class="inline-fields">
          <el-form-item label="抗原链 ID">
            <el-input v-model="targetChainId" style="width: 80px" />
          </el-form-item>
          <el-form-item label="重链链 ID">
            <el-input v-model="heavyChainId" style="width: 80px" />
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
            :rows="5"
            placeholder="vhh_id,sequence"
            class="mt-sm"
          />
          <el-input
            v-else
            v-model="heavyFastaInput"
            type="textarea"
            :rows="5"
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
            <el-button size="small">导入 CSV / Excel / FASTA</el-button>
          </el-upload>
          <p v-if="heavyFileHint" class="file-hint">{{ heavyFileHint }}</p>
          <p v-if="heavyPreview.length" class="file-hint">
            已识别 {{ heavyPreview.length }} 条重链
          </p>
        </el-form-item>
        <el-button type="primary" size="small" :loading="submitting" @click="submitBatch">
          开始批量预测
        </el-button>
      </el-form>
    </div>

    <div class="task-list-section">
      <div class="task-list-head">
        <h3>任务列表</h3>
        <el-button size="small" text :loading="store.loading" @click="store.refreshFoldTasks()">
          刷新
        </el-button>
      </div>
      <div class="task-filters">
        <button
          type="button"
          class="task-filter-btn"
          :class="{ active: store.taskFilter === 'all' }"
          @click="store.taskFilter = 'all'"
        >
          全部
        </button>
        <button
          type="button"
          class="task-filter-btn"
          :class="{ active: store.taskFilter === 'single' }"
          @click="store.taskFilter = 'single'"
        >
          单条
        </button>
        <button
          type="button"
          class="task-filter-btn"
          :class="{ active: store.taskFilter === 'batch' }"
          @click="store.taskFilter = 'batch'"
        >
          批次
        </button>
      </div>

      <div v-if="!store.mergedTaskItems.length" class="empty-state">暂无任务，请在上方提交预测</div>
      <div v-else class="task-list">
        <div
          v-for="item in store.mergedTaskItems"
          :key="item.kind + item.data.id"
          class="job-item task-item"
          :class="{
            active:
              (item.kind === 'single' && activeJobId === item.data.id) ||
              (item.kind === 'batch' && activeBatchId === item.data.id),
            'batch-item': item.kind === 'batch',
          }"
          @click="item.kind === 'single' ? openJob(item.data as Job) : openBatch(item.data as Batch)"
        >
          <div class="job-item-top">
            <div class="title">
              <span
                class="task-kind-badge"
                :class="item.kind === 'batch' ? 'kind-batch' : 'kind-single'"
              >
                {{ item.kind === 'batch' ? '批次' : '单条' }}
              </span>
              {{
                item.kind === 'single'
                  ? (item.data as Job).name || item.data.id.slice(0, 8)
                  : (item.data as Batch).name
              }}
            </div>
            <div class="job-item-actions" @click.stop>
              <el-tag :type="statusTagType(item.data.status)" size="small">
                {{
                  item.kind === 'batch'
                    ? batchStatusLabel(item.data.status)
                    : statusLabel(item.data.status)
                }}
              </el-tag>
              <button
                type="button"
                class="job-delete-btn"
                title="删除"
                @click="
                  item.kind === 'single'
                    ? onDeleteJob(item.data as Job)
                    : onDeleteBatch(item.data as Batch)
                "
              >
                ×
              </button>
            </div>
          </div>
          <div class="meta">
            <template v-if="item.kind === 'single'">
              {{
                Object.keys((item.data as Job).chains_json || {}).join(', ')
              }}
              · {{ (item.data as Job).total_length }} aa
              · {{ engineLabel((item.data as Job).engine) }}
              <template v-if="(item.data as Job).iptm != null">
                · ipTM {{ (item.data as Job).iptm!.toFixed(2) }}
              </template>
              · {{ formatTime(item.data.created_at) }}
            </template>
            <template v-else>
              {{ (item.data as Batch).target_name }}
              · {{ (item.data as Batch).done_count }}/{{ (item.data as Batch).heavy_chain_count }} 完成
              · {{ formatTime(item.data.created_at) }}
            </template>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
</style>
