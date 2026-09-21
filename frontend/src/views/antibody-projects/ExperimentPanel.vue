<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createExperiment,
  createSample,
  fetchCandidates,
  fetchExperiments,
  fetchSamples,
  fetchVersions,
  importAffinityXlsx,
  previewAffinityXlsx,
  type AffinityPreviewRow,
  type AntibodyCandidate,
  type AntibodyVersion,
  type Experiment,
  type SampleBatch,
} from '@/api/antibodyProjects'

const props = defineProps<{ projectId: string }>()
const candidates = ref<AntibodyCandidate[]>([])
const versions = ref<AntibodyVersion[]>([])
const samples = ref<SampleBatch[]>([])
const experiments = ref<Experiment[]>([])
const loading = ref(false)
const saving = ref(false)
const showSample = ref(false)
const showExperiment = ref(false)
const showAffinityImport = ref(false)
const affinityCandidateId = ref('')
const affinityFile = ref<File | null>(null)
const affinityPreview = ref<AffinityPreviewRow[]>([])
const affinitySummary = ref({ matched: 0, unmatched: 0, control: 0, duplicate: 0 })

const sampleForm = reactive({
  version_id: '',
  batch_code: '',
  expression_date: '',
  purification_date: '',
  concentration_value: undefined as number | undefined,
  concentration_unit: 'mg/mL',
  purity_percent: undefined as number | undefined,
  storage_location: '',
  notes: '',
})
const experimentForm = reactive({
  version_id: '',
  sample_batch_id: '',
  title: '',
  experiment_type: 'affinity',
  experiment_date: '',
  result_summary: '',
  notes: '',
  measurements: [
    { metric_name: 'KD', value_numeric: undefined as number | undefined, unit: 'nM' },
  ],
})

const usableVersions = computed(() => versions.value.filter((item) => item.status !== 'draft'))
const matchingSamples = computed(() =>
  samples.value.filter((item) => item.version_id === experimentForm.version_id),
)
const versionLabel = (id: string) => {
  const version = versions.value.find((item) => item.id === id)
  if (!version) return id.slice(0, 8)
  const candidate = candidates.value.find((item) => item.id === version.candidate_id)
  return candidate
    ? `${candidate.antibody_category || '待分类'} · ${candidate.candidate_code} · ${version.version_code}${version.name ? ` · ${version.name}` : ''}`
    : version.version_code
}

async function load() {
  loading.value = true
  try {
    candidates.value = await fetchCandidates(props.projectId)
    const versionGroups = await Promise.all(
      candidates.value.map((candidate) => fetchVersions(props.projectId, candidate.id)),
    )
    versions.value = versionGroups.flat()
    ;[samples.value, experiments.value] = await Promise.all([
      fetchSamples(props.projectId),
      fetchExperiments(props.projectId),
    ])
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '实验数据加载失败')
  } finally {
    loading.value = false
  }
}

function openSampleDialog() {
  sampleForm.version_id = usableVersions.value.at(-1)?.id || ''
  showSample.value = true
}

async function submitSample() {
  saving.value = true
  try {
    await createSample(props.projectId, {
      ...sampleForm,
      expression_date: sampleForm.expression_date || null,
      purification_date: sampleForm.purification_date || null,
      storage_location: sampleForm.storage_location || null,
      notes: sampleForm.notes || null,
    })
    showSample.value = false
    Object.assign(sampleForm, {
      batch_code: '',
      expression_date: '',
      purification_date: '',
      concentration_value: undefined,
      concentration_unit: 'mg/mL',
      purity_percent: undefined,
      storage_location: '',
      notes: '',
    })
    await load()
    ElMessage.success('样品批次已创建')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    saving.value = false
  }
}

const affinityCandidateVersions = computed(() =>
  versions.value.filter((item) => item.candidate_id === affinityCandidateId.value && item.status !== 'draft'),
)
const affinitySelectedCount = computed(
  () => affinityPreview.value.filter((item) => item.selected && item.version_id).length,
)

function statusText(status: string) {
  return {
    matched: '已匹配',
    unmatched: '未匹配',
    control: '对照已跳过',
    duplicate: '已导入过',
    draft: '版本未锁定',
  }[status] || status
}

function openAffinityImport() {
  affinityCandidateId.value = candidates.value[0]?.id || ''
  affinityFile.value = null
  affinityPreview.value = []
  affinitySummary.value = { matched: 0, unmatched: 0, control: 0, duplicate: 0 }
  showAffinityImport.value = true
}

async function onAffinityFile(uploadFile: { raw?: File }) {
  affinityFile.value = uploadFile.raw || null
  if (!affinityFile.value || !affinityCandidateId.value) return
  saving.value = true
  try {
    const preview = await previewAffinityXlsx(
      props.projectId,
      affinityCandidateId.value,
      affinityFile.value,
    )
    affinityPreview.value = preview.rows
    affinitySummary.value = {
      matched: preview.matched,
      unmatched: preview.unmatched,
      control: preview.control,
      duplicate: preview.duplicate,
    }
  } catch (error) {
    affinityPreview.value = []
    ElMessage.error(error instanceof Error ? error.message : '表格解析失败')
  } finally {
    saving.value = false
  }
}

watch(affinityCandidateId, () => {
  if (affinityFile.value) void onAffinityFile({ raw: affinityFile.value })
})

async function submitAffinityImport() {
  const items = affinityPreview.value.filter((item) => item.selected && item.version_id)
  if (!items.length) {
    ElMessage.warning('请勾选至少一行已指定版本的记录')
    return
  }
  saving.value = true
  try {
    const created = await importAffinityXlsx(props.projectId, affinityCandidateId.value, items)
    showAffinityImport.value = false
    await load()
    ElMessage.success(`已导入 ${created.length} 条亲和力实验`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '导入失败')
  } finally {
    saving.value = false
  }
}

function openExperimentDialog() {
  experimentForm.version_id = usableVersions.value.at(-1)?.id || ''
  experimentForm.sample_batch_id = ''
  showExperiment.value = true
}

function addMetric() {
  experimentForm.measurements.push({
    metric_name: '',
    value_numeric: undefined,
    unit: '',
  })
}

function removeMetric(index: number) {
  experimentForm.measurements.splice(index, 1)
}

async function submitExperiment() {
  saving.value = true
  try {
    await createExperiment(props.projectId, {
      ...experimentForm,
      sample_batch_id: experimentForm.sample_batch_id || null,
      experiment_date: experimentForm.experiment_date || null,
      result_summary: experimentForm.result_summary || null,
      notes: experimentForm.notes || null,
    })
    showExperiment.value = false
    Object.assign(experimentForm, {
      sample_batch_id: '',
      title: '',
      experiment_type: 'affinity',
      experiment_date: '',
      result_summary: '',
      notes: '',
      measurements: [{ metric_name: 'KD', value_numeric: undefined, unit: 'nM' }],
    })
    await load()
    ElMessage.success('实验结果已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => experimentForm.version_id, () => {
  experimentForm.sample_batch_id = ''
})
onMounted(load)
</script>

<template>
  <div v-loading="loading" class="experiment-panel">
    <section class="page-card resource-card">
      <div class="section-head">
        <div><h2>样品批次</h2><p>实验数据追溯到准确序列版本和样品批次</p></div>
        <el-button @click="openSampleDialog">新增样品</el-button>
      </div>
      <el-table :data="samples" size="small">
        <el-table-column prop="batch_code" label="批次号" min-width="120" />
        <el-table-column label="版本" width="90">
          <template #default="{ row }">{{ versionLabel(row.version_id) }}</template>
        </el-table-column>
        <el-table-column label="浓度" width="130">
          <template #default="{ row }">
            {{ row.concentration_value ?? '–' }} {{ row.concentration_unit || '' }}
          </template>
        </el-table-column>
        <el-table-column label="纯度" width="90">
          <template #default="{ row }">{{ row.purity_percent != null ? `${row.purity_percent}%` : '–' }}</template>
        </el-table-column>
        <el-table-column prop="storage_location" label="保存位置" min-width="150" />
      </el-table>
    </section>

    <section class="page-card resource-card">
      <div class="section-head">
        <div><h2>实验记录</h2><p>表达、纯度、亲和力、活性和稳定性</p></div>
        <div>
          <el-button @click="openAffinityImport">导入亲和力表格</el-button>
          <el-button type="primary" @click="openExperimentDialog">录入实验</el-button>
        </div>
      </div>
      <div class="experiment-list">
        <article v-for="experiment in experiments" :key="experiment.id" class="experiment-item">
          <div>
            <strong>{{ experiment.title }}</strong>
            <span>{{ versionLabel(experiment.version_id) }} · {{ experiment.experiment_type }}</span>
            <span v-if="experiment.conditions_json?.antigen">抗原 {{ experiment.conditions_json.antigen }}</span>
          </div>
          <div class="metric-list">
            <span v-for="metric in experiment.measurements" :key="metric.id">
              {{ metric.metric_name }} =
              {{ metric.value_numeric ?? metric.value_text }}
              {{ metric.unit || '' }}
            </span>
          </div>
          <small>{{ experiment.experiment_date || new Date(experiment.created_at).toLocaleDateString('zh-CN') }}</small>
        </article>
        <p v-if="!experiments.length" class="empty-note">暂无实验记录</p>
      </div>
    </section>

    <el-dialog v-model="showSample" title="新增样品批次" width="620px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="序列版本">
            <el-select v-model="sampleForm.version_id" style="width: 100%">
              <el-option v-for="item in usableVersions" :key="item.id" :label="item.version_code" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="批次号"><el-input v-model="sampleForm.batch_code" placeholder="EXP-001" /></el-form-item>
          <el-form-item label="表达日期"><el-date-picker v-model="sampleForm.expression_date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="纯化日期"><el-date-picker v-model="sampleForm.purification_date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="浓度">
            <el-input-number v-model="sampleForm.concentration_value" :min="0" :precision="3" />
          </el-form-item>
          <el-form-item label="浓度单位"><el-input v-model="sampleForm.concentration_unit" /></el-form-item>
          <el-form-item label="纯度 %"><el-input-number v-model="sampleForm.purity_percent" :min="0" :max="100" :precision="2" /></el-form-item>
          <el-form-item label="保存位置"><el-input v-model="sampleForm.storage_location" /></el-form-item>
        </div>
        <el-form-item label="备注"><el-input v-model="sampleForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSample = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitSample">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showExperiment" title="录入实验结果" width="720px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="序列版本">
            <el-select v-model="experimentForm.version_id" style="width: 100%">
              <el-option v-for="item in usableVersions" :key="item.id" :label="item.version_code" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="样品批次">
            <el-select v-model="experimentForm.sample_batch_id" clearable style="width: 100%">
              <el-option v-for="item in matchingSamples" :key="item.id" :label="item.batch_code" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="实验名称"><el-input v-model="experimentForm.title" /></el-form-item>
          <el-form-item label="实验类型">
            <el-select v-model="experimentForm.experiment_type" style="width: 100%">
              <el-option label="表达量" value="expression" />
              <el-option label="纯度/聚集" value="purity" />
              <el-option label="亲和力" value="affinity" />
              <el-option label="活性" value="activity" />
              <el-option label="稳定性" value="stability" />
              <el-option label="自定义" value="custom" />
            </el-select>
          </el-form-item>
          <el-form-item label="实验日期"><el-date-picker v-model="experimentForm.experiment_date" value-format="YYYY-MM-DD" /></el-form-item>
        </div>
        <el-form-item label="测量指标">
          <div class="metrics-editor">
            <div v-for="(metric, index) in experimentForm.measurements" :key="index" class="metric-row">
              <el-input v-model="metric.metric_name" placeholder="KD / Tm / EC50" />
              <el-input-number v-model="metric.value_numeric" :controls="false" placeholder="数值" />
              <el-input v-model="metric.unit" placeholder="单位" />
              <el-button text type="danger" @click="removeMetric(index)">移除</el-button>
            </div>
            <el-button text type="primary" @click="addMetric">+ 添加指标</el-button>
          </div>
        </el-form-item>
        <el-form-item label="实验结论"><el-input v-model="experimentForm.result_summary" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="experimentForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExperiment = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitExperiment">保存实验</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAffinityImport" title="导入亲和力表格" width="1080px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="候选抗体">
            <el-select v-model="affinityCandidateId" style="width: 100%">
              <el-option
                v-for="candidate in candidates"
                :key="candidate.id"
                :label="`[${candidate.antibody_category || '待分类'}] ${candidate.candidate_code} · ${candidate.name}`"
                :value="candidate.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="Excel 文件">
            <el-upload
              drag
              :auto-upload="false"
              :limit="1"
              accept=".xlsx,.xlsm"
              :on-change="onAffinityFile"
              :on-remove="() => { affinityFile = null; affinityPreview = [] }"
            >
              <div class="el-upload__text">只读取工作表「亲和力」</div>
            </el-upload>
          </el-form-item>
        </div>
      </el-form>
      <p v-if="affinityPreview.length" class="empty-note">
        已匹配 {{ affinitySummary.matched }} 行，未匹配 {{ affinitySummary.unmatched }} 行，对照 {{ affinitySummary.control }} 行已跳过。
      </p>
      <el-table v-if="affinityPreview.length" :data="affinityPreview" size="small" max-height="420">
        <el-table-column label="导入" width="70">
          <template #default="{ row }">
            <el-checkbox v-model="row.selected" :disabled="row.status === 'control' || !row.version_id" />
          </template>
        </el-table-column>
        <el-table-column prop="excel_row" label="行" width="60" />
        <el-table-column prop="loading_sample_id" label="上样样品" min-width="180" />
        <el-table-column prop="antigen" label="抗原" min-width="120" />
        <el-table-column label="KD (M)" width="110">
          <template #default="{ row }">{{
            row.kd_m == null ? '–' : `${row.kd_qualifier || ''}${row.kd_m.toExponential(2)}`
          }}</template>
        </el-table-column>
        <el-table-column prop="result" label="结果" width="90" />
        <el-table-column label="版本" min-width="220">
          <template #default="{ row }">
            <el-select
              v-model="row.version_id"
              clearable
              filterable
              :disabled="row.status === 'control'"
              placeholder="指定版本"
              style="width: 100%"
              @change="row.selected = Boolean(row.version_id) && row.status !== 'duplicate'"
            >
              <el-option
                v-for="version in affinityCandidateVersions"
                :key="version.id"
                :label="`${version.version_code}${version.name ? ' · ' + version.name : ''}`"
                :value="version.id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="140">
          <template #default="{ row }">{{ statusText(row.status) }}{{ row.message ? ` · ${row.message}` : '' }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="showAffinityImport = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!affinitySelectedCount" @click="submitAffinityImport">
          导入 {{ affinitySelectedCount }} 条
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.experiment-panel { display: grid; gap: 1rem; }
.resource-card { padding: 1rem; }
.experiment-list { display: grid; gap: 0.6rem; }
.experiment-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) auto;
  gap: 1rem;
  align-items: start;
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;

  div:first-child { display: grid; }
  span, small { color: var(--muted); font-size: 0.76rem; }
}
.metric-list { display: flex; flex-wrap: wrap; gap: 0.45rem; }
.metric-list span { padding: 0.2rem 0.45rem; border-radius: 6px; background: var(--bio-green-light); color: var(--bio-green-dark); }
.metrics-editor { width: 100%; display: grid; gap: 0.45rem; }
.metric-row { display: grid; grid-template-columns: 1.5fr 1fr 1fr auto; gap: 0.45rem; }

@media (max-width: 760px) {
  .experiment-item, .metric-row { grid-template-columns: 1fr; }
}
</style>
