<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import {
  createCandidate,
  createVersion,
  fetchCandidates,
  fetchExperiments,
  fetchJobLinks,
  fetchVersions,
  foldAntibodyOnly,
  importVersions,
  importVersionsFromFasta,
  importVersionsFromXlsx,
  deleteVersion,
  lockDraftVersions,
  lockVersion,
  setCandidateCategory,
  type AntibodyCandidate,
  type AntibodyVersion,
  type Experiment,
  type ProjectJobLink,
  type VersionChain,
} from '@/api/antibodyProjects'
import ChainSequencePair from './ChainSequencePair.vue'
import VersionStructurePanel from './VersionStructurePanel.vue'

const props = withDefaults(defineProps<{ projectId: string; visible?: boolean }>(), {
  visible: true,
})
const router = useRouter()
const candidates = ref<AntibodyCandidate[]>([])
const versions = ref<AntibodyVersion[]>([])
const experiments = ref<Experiment[]>([])
const jobLinks = ref<ProjectJobLink[]>([])
const folding = ref(false)
const activeCandidateId = ref('')
const activeVersionId = ref('')
const loading = ref(false)
const saving = ref(false)
const showCandidate = ref(false)
const showVersion = ref(false)
const showImport = ref(false)
const showCategory = ref(false)
const pendingCategory = ref<'RM' | 'RN' | 'RL'>('RM')

const candidateForm = reactive({
  candidate_code: '',
  name: '',
  antibody_category: '' as '' | 'RM' | 'RN' | 'RL',
  antibody_type: 'igg' as 'igg' | 'vhh',
  description: '',
  vh: '',
  vl: '',
  vhh: '',
  full_vh: '',
  full_vl: '',
  full_vhh: '',
})
const versionForm = reactive({
  parent_version_id: '',
  name: '',
  vh: '',
  vl: '',
  vhh: '',
  full_vh: '',
  full_vl: '',
  full_vhh: '',
})
const importForm = reactive({
  parent_version_id: '',
  text: '',
  file: null as File | null,
})
const importFileList = ref<UploadFile[]>([])

const activeCandidate = computed(() =>
  candidates.value.find((item) => item.id === activeCandidateId.value),
)
const activeVersion = computed(() =>
  versions.value.find((item) => item.id === activeVersionId.value),
)
const parentVersion = computed(() =>
  versions.value.find((item) => item.id === activeVersion.value?.primary_parent_id),
)

function parentChainFor(chain: VersionChain) {
  return parentVersion.value?.chains.find((item) => item.chain_role === chain.chain_role) || null
}

function versionDisplayName(version: AntibodyVersion | undefined) {
  if (!version) return '母本'
  return version.name ? `${version.version_code} · ${version.name}` : version.version_code
}
const parentChoices = computed(() =>
  versions.value.filter((item) => item.status !== 'draft'),
)

function roundKey(code: string) {
  if (code.toUpperCase() === 'WT') return 'WT'
  const matched = code.match(/^M(\d+)/i)
  return matched ? `M${matched[1]}` : code
}

const lineageGroups = computed(() => {
  const grouped = new Map<string, AntibodyVersion[]>()
  for (const version of versions.value) {
    const key = roundKey(version.version_code)
    const bucket = grouped.get(key)
    if (bucket) bucket.push(version)
    else grouped.set(key, [version])
  }
  return [...grouped.entries()].map(([key, items]) => ({
    key,
    label: key === 'WT' ? '母本' : `第 ${key.slice(1)} 轮 · ${key}（${items.length} 条，同一层级）`,
    draftCount: items.filter((item) => item.status === 'draft').length,
    items,
  }))
})

const allDraftCount = computed(
  () => versions.value.filter((item) => item.status === 'draft' && item.version_code.toUpperCase() !== 'WT').length,
)

function versionNameParts(name: string | null) {
  if (!name?.trim()) return []
  return name.split('|').map((part) => part.trim()).filter(Boolean)
}

const statusText: Record<string, string> = {
  draft: '草稿',
  locked: '已锁定',
  tested: '已实验',
  rejected: '已淘汰',
}
const mutationText: Record<string, string> = {
  substitution: '替换',
  insertion: '插入',
  deletion: '删除',
}

type ImpactTone = 'better' | 'worse' | 'same' | 'na'

interface AntigenImpact {
  kd: number | null
  result: string | null
  kdText: string
  vsParent: string
  tone: ImpactTone
}

function metricOf(experiment: Experiment, name: string) {
  return experiment.measurements.find((item) => item.metric_name === name)
}

function experimentAntigen(experiment: Experiment) {
  const raw = experiment.conditions_json?.antigen
  return typeof raw === 'string' && raw.trim() ? raw.trim() : '未标注抗原'
}

function experimentKd(experiment: Experiment) {
  const metric = metricOf(experiment, 'KD')
  if (metric?.value_numeric == null) return null
  if ((metric.unit || '').toLowerCase() === 'nm') return metric.value_numeric * 1e-9
  return metric.value_numeric
}

function experimentResult(experiment: Experiment) {
  return metricOf(experiment, 'result')?.value_text || experiment.result_summary || null
}

function isNoBind(kd: number | null, result: string | null) {
  if (kd != null) return false
  return !!result && /^(nb|neg|no[\s_-]*bind)/i.test(result.trim())
}

function experimentQualifier(experiment: Experiment, name: string) {
  return metricOf(experiment, name)?.qualifier || null
}

function limitPrefix(qualifier: string | null) {
  if (!qualifier) return ''
  if (qualifier === '<' || qualifier === '<=') return '<'
  if (qualifier === '>' || qualifier === '>=') return '>'
  return ''
}

function formatKd(kd: number | null, result: string | null, qualifier: string | null = null) {
  if (kd == null) {
    if (isNoBind(kd, result)) return '无结合'
    return result || '–'
  }
  const prefix = limitPrefix(qualifier)
  if (kd > 0 && kd < 1e-4) return `${prefix}${(kd * 1e9).toPrecision(3)} nM`
  return `${prefix}${kd.toExponential(2)} M`
}

function mutationLabel(version: AntibodyVersion) {
  if (!version.mutations.length) return version.version_code.toUpperCase() === 'WT' ? '母本' : '与父本相同'
  return version.mutations.map((item) => {
    const change = item.mutation_type === 'substitution'
      ? `${item.from_aa || '?'}${item.sequence_position ?? ''}${item.to_aa || '?'}`
      : `${mutationText[item.mutation_type] || item.mutation_type}${item.sequence_position ?? ''}`
    return item.region && item.region !== 'FW' ? `${change}（${item.region}）` : change
  }).join('、')
}

function isCensoredLow(qualifier: string | null | undefined) {
  return qualifier === '<' || qualifier === '<='
}

function compareToParent(
  childKd: number | null,
  childResult: string | null,
  parentKd: number | null,
  parentResult: string | null,
  childQualifier: string | null = null,
  parentQualifier: string | null = null,
): { text: string; tone: ImpactTone } {
  const childNeg = isNoBind(childKd, childResult)
  const parentNeg = isNoBind(parentKd, parentResult)
  const childLow = isCensoredLow(childQualifier)
  const parentLow = isCensoredLow(parentQualifier)
  if (childLow && parentLow) return { text: '都低于检测限', tone: 'same' }
  if (parentLow && childKd != null && parentKd != null && childKd > parentKd * 1.15) {
    return { text: '弱于检测下限', tone: 'worse' }
  }
  if (childLow && parentKd != null && childKd != null && childKd < parentKd / 1.15) {
    return { text: '仍低于检测限', tone: 'better' }
  }
  if (childKd != null && parentKd != null && childKd > 0 && parentKd > 0) {
    const fold = parentKd / childKd
    if (fold >= 1.15) return { text: `好 ${fold.toFixed(1)}×`, tone: 'better' }
    if (fold <= 1 / 1.15) return { text: `差 ${(1 / fold).toFixed(1)}×`, tone: 'worse' }
    return { text: '接近父本', tone: 'same' }
  }
  if (childNeg && parentKd != null) return { text: '变为无结合', tone: 'worse' }
  if (childKd != null && parentNeg) return { text: '恢复结合', tone: 'better' }
  return { text: '–', tone: 'na' }
}

const candidateExperiments = computed(() => {
  const ids = new Set(versions.value.map((item) => item.id))
  return experiments.value.filter((item) => ids.has(item.version_id) && item.experiment_type === 'affinity')
})

const physchemColumns = [
  { key: 'SEC_monomer', label: 'SEC 单体', unit: '%', better: 'higher' as const },
  { key: 'HIC_RT', label: 'HIC', unit: 'min', better: 'lower' as const },
  { key: 'Tm1', label: 'Tm1', unit: '°C', better: 'higher' as const },
  { key: 'Tm2', label: 'Tm2', unit: '°C', better: 'higher' as const },
  { key: 'Tagg', label: 'Tagg', unit: '°C', better: 'higher' as const },
  { key: 'pI', label: 'pI', unit: '', better: 'none' as const },
]

const candidatePhyschem = computed(() => {
  const ids = new Set(versions.value.map((item) => item.id))
  return experiments.value.filter((item) => ids.has(item.version_id) && item.experiment_type === 'physicochemical')
})

function physchemValue(versionId: string, metric: string) {
  const experiments = candidatePhyschem.value.filter((item) => item.version_id === versionId)
  for (const experiment of experiments) {
    const measurement = metricOf(experiment, metric)
    if (measurement?.value_numeric != null) return measurement.value_numeric
  }
  if (metric !== 'Tm1') return null
  for (const experiment of experiments) {
    const legacy = metricOf(experiment, 'Tm')
    if (legacy?.value_numeric != null) return legacy.value_numeric
  }
  return null
}

function measuredPhyschem(row: Record<string, unknown>) {
  const physchem = row.physchem as Record<string, { text: string; vsParent: string; tone: ImpactTone }> | undefined
  return physchemColumns.flatMap((column) => {
    const cell = physchem?.[column.key]
    if (!cell || cell.text === '未测') return []
    return [{ key: column.key, label: column.label, ...cell }]
  })
}

function formatPhyschem(value: number | null, unit: string) {
  if (value == null) return '未测'
  const text = Number.isInteger(value) ? String(value) : value.toPrecision(3).replace(/\.?0+$/, '')
  return unit ? `${text} ${unit}` : text
}

function comparePhyschem(
  child: number | null,
  parent: number | null,
  better: 'higher' | 'lower' | 'none',
): { text: string; tone: ImpactTone } {
  if (better === 'none' || child == null || parent == null) return { text: '–', tone: 'na' }
  const scale = Math.max(Math.abs(parent), 1e-9)
  if (Math.abs(child - parent) / scale < 0.02) return { text: '接近父本', tone: 'same' }
  const improved = better === 'higher' ? child > parent : child < parent
  return { text: improved ? '好于父本' : '差于父本', tone: improved ? 'better' : 'worse' }
}

const impactAntigens = computed(() => {
  const names = new Set(candidateExperiments.value.map(experimentAntigen))
  return [...names].sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const impactTableKey = computed(() => impactAntigens.value.join('|'))

function hitsForVersion(versionId: string) {
  const byAntigen = new Map<string, { kd: number | null; result: string | null; qualifier: string | null }>()
  for (const experiment of candidateExperiments.value) {
    if (experiment.version_id !== versionId) continue
    const antigen = experimentAntigen(experiment)
    const next = {
      kd: experimentKd(experiment),
      result: experimentResult(experiment),
      qualifier: experimentQualifier(experiment, 'KD'),
    }
    const current = byAntigen.get(antigen)
    if (!current || (current.kd == null && next.kd != null)) {
      byAntigen.set(antigen, next)
    }
  }
  return byAntigen
}

const impactRows = computed(() => {
  return versions.value.map((version) => {
    const parent = versions.value.find((item) => item.id === version.primary_parent_id)
    const childHits = hitsForVersion(version.id)
    const parentHits = parent ? hitsForVersion(parent.id) : new Map()
    const byAntigen: Record<string, AntigenImpact> = {}
    for (const antigen of impactAntigens.value) {
      const child = childHits.get(antigen)
      const parentHit = parentHits.get(antigen)
      const vs = version.primary_parent_id
        ? compareToParent(
            child?.kd ?? null,
            child?.result ?? null,
            parentHit?.kd ?? null,
            parentHit?.result ?? null,
            child?.qualifier ?? null,
            parentHit?.qualifier ?? null,
          )
        : { text: '基准', tone: 'na' as ImpactTone }
      byAntigen[antigen] = {
        kd: child?.kd ?? null,
        result: child?.result ?? null,
        kdText: child ? formatKd(child.kd, child.result, child.qualifier) : '未测',
        vsParent: vs.text,
        tone: vs.tone,
      }
    }
    const physchem: Record<string, { text: string; vsParent: string; tone: ImpactTone }> = {}
    for (const column of physchemColumns) {
      const child = physchemValue(version.id, column.key)
      const parentValue = parent ? physchemValue(parent.id, column.key) : null
      const vs = version.primary_parent_id
        ? comparePhyschem(child, parentValue, column.better)
        : { text: '基准', tone: 'na' as ImpactTone }
      physchem[column.key] = {
        text: formatPhyschem(child, column.unit),
        vsParent: child == null ? '–' : vs.text,
        tone: child == null ? 'na' : vs.tone,
      }
    }
    return {
      id: version.id,
      version_code: version.version_code,
      name: version.name,
      parentCode: parent?.version_code || '',
      mutations: mutationLabel(version),
      byAntigen,
      physchem,
    }
  }).sort((a, b) => {
    if (!a.parentCode && b.parentCode) return -1
    if (a.parentCode && !b.parentCode) return 1
    return a.version_code.localeCompare(b.version_code, 'zh-CN', { numeric: true })
  })
})

const patternNotes = computed(() => {
  const notes: string[] = []
  const variants = impactRows.value.filter((row) => row.parentCode)
  if (!variants.length) return notes
  for (const antigen of impactAntigens.value) {
    const judged = variants.filter((row) => ['better', 'worse', 'same'].includes(row.byAntigen[antigen]?.tone || ''))
    if (!judged.length) continue
    const better = judged.filter((row) => row.byAntigen[antigen].tone === 'better')
    const worse = judged.filter((row) => row.byAntigen[antigen].tone === 'worse')
    const same = judged.length - better.length - worse.length
    const worseText = worse.slice(0, 4).map((row) => `${row.version_code} ${row.mutations}`).join('；')
    notes.push(
      `${antigen}：${judged.length} 个改造里，${better.length} 个好于或仍低于检测限，${same} 个接近，${worse.length} 个变弱。`
      + (worseText ? `变弱的有 ${worseText}${worse.length > 4 ? ' 等' : ''}。` : ''),
    )
  }
  const hicRows = variants
    .map((row) => ({ row, value: physchemValue(row.id, 'HIC_RT') }))
    .filter((item): item is { row: typeof variants[number]; value: number } => item.value != null)
  if (hicRows.length >= 2) {
    const values = hicRows.map((item) => item.value)
    const low = Math.min(...values)
    const high = Math.max(...values)
    const antigen = impactAntigens.value[0]
    const highCut = low + (high - low) * 0.5
    const hydrophobic = antigen
      ? hicRows.filter((item) => item.value >= highCut && item.row.byAntigen[antigen]?.tone === 'worse')
      : []
    notes.push(
      `HIC 已测 ${hicRows.length} 条，${low.toPrecision(3)}–${high.toPrecision(3)} min。`
      + (hydrophobic.length
        ? `保留时间偏高、同时亲和力变弱的有 ${hydrophobic.map((item) => item.row.version_code).join('、')}。`
        : '保留时间高低和亲和力变弱没有挤在同一批版本上。'),
    )
  }
  return notes
})

const activePhyschem = computed(() =>
  candidatePhyschem.value.find((item) => item.version_id === activeVersionId.value) || null,
)

const activePhyschemRows = computed(() => {
  const version = versions.value.find((item) => item.id === activeVersionId.value)
  const parent = versions.value.find((item) => item.id === version?.primary_parent_id)
  return physchemColumns.map((column) => {
    const child = version ? physchemValue(version.id, column.key) : null
    const parentValue = parent ? physchemValue(parent.id, column.key) : null
    const vs = version?.primary_parent_id
      ? comparePhyschem(child, parentValue, column.better)
      : { text: '基准', tone: 'na' as ImpactTone }
    return {
      label: column.label,
      text: formatPhyschem(child, column.unit),
      vsParent: child == null ? '–' : vs.text,
      tone: child == null ? 'na' : vs.tone,
    }
  })
})

const activeVersionExperiments = computed(() =>
  candidateExperiments.value
    .filter((item) => item.version_id === activeVersionId.value)
    .map((item) => ({
      id: item.id,
      antigen: experimentAntigen(item),
      result: experimentResult(item) || '–',
      kd: experimentMetric(item, 'KD'),
      ka: experimentMetric(item, 'ka'),
      kdis: experimentMetric(item, 'kdis'),
      title: item.title,
    })),
)

const candidateFoldLinks = computed(() => {
  const ids = new Set(versions.value.map((item) => item.id))
  return jobLinks.value.filter(
    (item) => ids.has(item.version_id) && item.purpose === 'fold_antibody',
  )
})

const activeVersionFoldLinks = computed(() =>
  candidateFoldLinks.value.filter((item) => item.version_id === activeVersionId.value),
)

const activeFoldJobId = computed(() => {
  const link = activeVersionFoldLinks.value[0]
  return link ? (link.job_id || link.original_job_id) : ''
})

const parentFoldJobId = computed(() => {
  const parentId = activeVersion.value?.primary_parent_id
  if (!parentId) return ''
  const link = jobLinks.value.find(
    (item) => item.version_id === parentId && item.purpose === 'fold_antibody',
  )
  return link ? (link.job_id || link.original_job_id) : ''
})

function openFoldBatch(batchId: string) {
  router.push({ name: 'fold-batch', params: { id: batchId } })
}

function selectImpactRow(row: { id: string }) {
  activeVersionId.value = row.id
}

function experimentMetric(experiment: Experiment, name: string) {
  const metric = metricOf(experiment, name)
  if (name === 'KD') {
    return formatKd(experimentKd(experiment), experimentResult(experiment), experimentQualifier(experiment, 'KD'))
  }
  if (!metric) return '–'
  if (metric.value_numeric != null) {
    return `${limitPrefix(metric.qualifier)}${metric.value_numeric.toExponential(2)}`
  }
  return metric.value_text || '–'
}

async function loadCandidates() {
  loading.value = true
  try {
    candidates.value = await fetchCandidates(props.projectId)
    if (!activeCandidateId.value && candidates.value.length) {
      activeCandidateId.value = candidates.value[0].id
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '候选抗体加载失败')
  } finally {
    loading.value = false
  }
}

async function loadVersions() {
  if (!activeCandidateId.value) {
    versions.value = []
    experiments.value = []
    return
  }
  loading.value = true
  try {
    const [versionRows, experimentRows, linkRows] = await Promise.all([
      fetchVersions(props.projectId, activeCandidateId.value),
      fetchExperiments(props.projectId),
      fetchJobLinks(props.projectId),
    ])
    versions.value = versionRows
    experiments.value = experimentRows
    jobLinks.value = linkRows
    if (!versions.value.some((item) => item.id === activeVersionId.value)) {
      activeVersionId.value = versions.value.at(-1)?.id || ''
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '版本加载失败')
  } finally {
    loading.value = false
  }
}

function candidateChains() {
  return candidateForm.antibody_type === 'igg'
    ? [
        { chain_role: 'VH', variable_sequence: candidateForm.vh, full_sequence: candidateForm.full_vh || null },
        { chain_role: 'VL', variable_sequence: candidateForm.vl, full_sequence: candidateForm.full_vl || null },
      ]
    : [{ chain_role: 'VHH', variable_sequence: candidateForm.vhh, full_sequence: candidateForm.full_vhh || null }]
}

async function submitCandidate() {
  if (!candidateForm.antibody_category) {
    ElMessage.warning('请选择 RM、RN 或 RL')
    return
  }
  saving.value = true
  try {
    const candidate = await createCandidate(props.projectId, {
      candidate_code: candidateForm.candidate_code.trim(),
      name: candidateForm.name.trim(),
      antibody_category: candidateForm.antibody_category as 'RM' | 'RN' | 'RL',
      antibody_type: candidateForm.antibody_type,
      description: candidateForm.description.trim() || undefined,
      chains: candidateChains(),
    })
    showCandidate.value = false
    Object.assign(candidateForm, {
      candidate_code: '',
      name: '',
      antibody_category: '',
      antibody_type: 'igg',
      description: '',
      vh: '',
      vl: '',
      vhh: '',
      full_vh: '',
      full_vl: '',
      full_vhh: '',
    })
    await loadCandidates()
    activeCandidateId.value = candidate.id
    ElMessage.success('候选抗体和 WT 已创建')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    saving.value = false
  }
}

async function submitCategory() {
  if (!activeCandidate.value) return
  saving.value = true
  try {
    await setCandidateCategory(
      props.projectId,
      activeCandidate.value.id,
      pendingCategory.value,
    )
    showCategory.value = false
    await loadCandidates()
    ElMessage.success('抗体分类已设置，后续不能修改')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分类失败')
  } finally {
    saving.value = false
  }
}

function openVersionDialog() {
  const parent = activeVersion.value && activeVersion.value.status !== 'draft'
    ? activeVersion.value
    : parentChoices.value.at(-1)
  if (!parent) return
  versionForm.parent_version_id = parent.id
  versionForm.name = ''
  versionForm.vh = parent.chains.find((item) => item.chain_role === 'VH')?.variable_sequence || ''
  versionForm.vl = parent.chains.find((item) => item.chain_role === 'VL')?.variable_sequence || ''
  versionForm.vhh = parent.chains.find((item) => item.chain_role === 'VHH')?.variable_sequence || ''
  versionForm.full_vh = parent.chains.find((item) => item.chain_role === 'VH')?.full_sequence || ''
  versionForm.full_vl = parent.chains.find((item) => item.chain_role === 'VL')?.full_sequence || ''
  versionForm.full_vhh = parent.chains.find((item) => item.chain_role === 'VHH')?.full_sequence || ''
  showVersion.value = true
}

function versionChains() {
  return activeCandidate.value?.antibody_type === 'vhh'
    ? [{ chain_role: 'VHH', variable_sequence: versionForm.vhh, full_sequence: versionForm.full_vhh || null }]
    : [
        { chain_role: 'VH', variable_sequence: versionForm.vh, full_sequence: versionForm.full_vh || null },
        { chain_role: 'VL', variable_sequence: versionForm.vl, full_sequence: versionForm.full_vl || null },
      ]
}

async function submitVersion() {
  if (!activeCandidate.value) return
  saving.value = true
  try {
    const version = await createVersion(props.projectId, activeCandidate.value.id, {
      parent_version_id: versionForm.parent_version_id,
      name: versionForm.name.trim() || undefined,
      chains: versionChains(),
    })
    showVersion.value = false
    await loadVersions()
    activeVersionId.value = version.id
    ElMessage.success(`${version.version_code} 已创建`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    saving.value = false
  }
}

function defaultParentId() {
  const parent = activeVersion.value && activeVersion.value.status !== 'draft'
    ? activeVersion.value
    : parentChoices.value.at(-1)
  return parent?.id || ''
}

function openImportDialog() {
  if (!defaultParentId()) return
  importForm.parent_version_id = defaultParentId()
  importForm.text = ''
  importForm.file = null
  importFileList.value = []
  showImport.value = true
}

function onFastaFileChange(uploadFile: UploadFile) {
  importForm.file = uploadFile.raw || null
}

function onFastaFileRemove() {
  importForm.file = null
}

function parseNamedSequences(text: string): Array<{ name?: string; sequence: string }> {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (trimmed.includes('>')) {
    const records: Array<{ name?: string; sequence: string }> = []
    let name = ''
    const chunks: string[] = []
    const flush = () => {
      const sequence = chunks.join('').replace(/\s+/g, '')
      if (sequence) records.push({ name: name || undefined, sequence })
      name = ''
      chunks.length = 0
    }
    for (const line of trimmed.split(/\r?\n/)) {
      if (line.startsWith('>')) {
        flush()
        name = line.slice(1).trim()
      } else {
        chunks.push(line.trim())
      }
    }
    flush()
    return records
  }
  return trimmed.split(/\r?\n/).flatMap((line) => {
    const sequence = line.trim().replace(/\s+/g, '')
    return sequence ? [{ sequence }] : []
  })
}

function parseIggRows(text: string) {
  const rows: Array<{ name?: string; vh: string; vl: string }> = []
  for (const line of text.trim().split(/\r?\n/)) {
    const parts = line.split(/\t|,/).map((item) => item.trim())
    if (parts.length < 2 || !parts.some(Boolean)) continue
    if (/^(name|名称|id)$/i.test(parts[0]) && /^vh$/i.test(parts[1] || '')) continue
    if (parts.length === 2) {
      rows.push({ vh: parts[0], vl: parts[1] })
    } else {
      rows.push({ name: parts[0] || undefined, vh: parts[1], vl: parts[2] })
    }
  }
  return rows
}

async function submitImport() {
  if (!activeCandidate.value) return
  saving.value = true
  try {
    let versionsCreated
    if (importForm.file) {
      const filename = importForm.file.name.toLowerCase()
      if (filename.endsWith('.xlsx') || filename.endsWith('.xlsm')) {
        versionsCreated = await importVersionsFromXlsx(
          props.projectId,
          activeCandidate.value.id,
          importForm.parent_version_id,
          importForm.file,
        )
      } else {
        versionsCreated = await importVersionsFromFasta(
          props.projectId,
          activeCandidate.value.id,
          importForm.parent_version_id,
          importForm.file,
        )
      }
    } else {
      const items = activeCandidate.value.antibody_type === 'vhh'
        ? parseNamedSequences(importForm.text).map((item) => ({
            name: item.name,
            chains: [{ chain_role: 'VHH', variable_sequence: item.sequence }],
          }))
        : parseIggRows(importForm.text).map((item) => ({
            name: item.name,
            chains: [
              { chain_role: 'VH', variable_sequence: item.vh },
              { chain_role: 'VL', variable_sequence: item.vl },
            ],
          }))
      if (!items.length) {
        ElMessage.warning('请先选择 FASTA 文件，或粘贴序列')
        return
      }
      versionsCreated = await importVersions(
        props.projectId,
        activeCandidate.value.id,
        {
          parent_version_id: importForm.parent_version_id,
          items,
        },
      )
    }
    showImport.value = false
    await loadVersions()
    activeVersionId.value = versionsCreated.at(-1)?.id || ''
    ElMessage.success(`已导入 ${versionsCreated.length} 条：${versionsCreated[0].version_code} 至 ${versionsCreated.at(-1)?.version_code}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '导入失败')
  } finally {
    saving.value = false
  }
}

async function submitFold(versionIds?: string[]) {
  if (!activeCandidate.value) return
  const count = versionIds?.length || versions.value.length
  if (!count) {
    ElMessage.warning('没有可折叠的版本')
    return
  }
  const scope = versionIds?.length === 1
    ? `当前版本 ${activeVersion.value?.version_code}`
    : `本候选的 ${count} 个版本`
  try {
    await ElMessageBox.confirm(
      `将提交 ${scope} 的抗体自身折叠（不含抗原）。IgG 用 VH+VL，VHH 只用重链。已有折叠任务的版本会跳过。`,
      '折叠抗体结构',
      { type: 'info', confirmButtonText: '开始折叠' },
    )
  } catch {
    return
  }
  folding.value = true
  try {
    const result = await foldAntibodyOnly(props.projectId, versionIds?.length
      ? { version_ids: versionIds }
      : { candidate_id: activeCandidate.value.id })
    await loadVersions()
    ElMessage.success(`已提交 ${result.job_ids.length} 个折叠任务`)
    if (result.batch_id) openFoldBatch(result.batch_id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '提交折叠失败')
  } finally {
    folding.value = false
  }
}

async function doDelete() {
  if (!activeVersion.value) return
  const label = activeVersion.value.name
    ? `${activeVersion.value.version_code} · ${activeVersion.value.name}`
    : activeVersion.value.version_code
  try {
    await ElMessageBox.confirm(
      `删除草稿 ${label} 后，这条序列和对应的突变记录会一起去掉，且不能恢复。`,
      '删除序列',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await deleteVersion(props.projectId, activeVersion.value.id)
    await loadVersions()
    ElMessage.success('序列已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

async function doLock() {
  if (!activeVersion.value) return
  try {
    await ElMessageBox.confirm(
      `锁定 ${activeVersion.value.version_code} 后将不能再修改序列，是否继续？`,
      '锁定版本',
      { type: 'warning' },
    )
    await lockVersion(props.projectId, activeVersion.value.id)
    await loadVersions()
    ElMessage.success('版本已锁定')
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error instanceof Error ? error.message : '锁定失败')
  }
}

async function doLockDrafts(roundCode?: string, count = allDraftCount.value) {
  if (!activeCandidate.value || !count) return
  const label = roundCode ? `${roundCode} 的 ${count} 条草稿` : `全部 ${count} 条草稿`
  try {
    await ElMessageBox.confirm(
      `锁定${label}后将不能再修改序列，是否继续？`,
      '批量锁定',
      { type: 'warning' },
    )
    const locked = await lockDraftVersions(
      props.projectId,
      activeCandidate.value.id,
      roundCode,
    )
    await loadVersions()
    ElMessage.success(`已锁定 ${locked.length} 条`)
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error instanceof Error ? error.message : '锁定失败')
  }
}

async function reloadExperiments() {
  if (!activeCandidateId.value) return
  try {
    experiments.value = await fetchExperiments(props.projectId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '亲和力数据刷新失败')
  }
}

watch(activeCandidateId, loadVersions)
watch(() => props.visible, (visible, wasVisible) => {
  if (visible && wasVisible === false) void reloadExperiments()
})
onMounted(loadCandidates)
</script>

<template>
  <div v-loading="loading" class="version-workspace">
    <section class="page-card candidate-bar">
      <div class="candidate-picker">
        <span class="field-label">候选抗体</span>
        <el-select v-model="activeCandidateId" placeholder="选择候选抗体">
          <el-option
            v-for="candidate in candidates"
            :key="candidate.id"
            :label="`[${candidate.antibody_category || '待分类'}] ${candidate.candidate_code} · ${candidate.name}`"
            :value="candidate.id"
          />
        </el-select>
      </div>
      <div class="candidate-actions">
        <el-button
          v-if="activeCandidate && !activeCandidate.antibody_category"
          type="warning"
          plain
          @click="showCategory = true"
        >
          设置 RM/RN/RL
        </el-button>
        <el-button @click="showCandidate = true">添加候选抗体</el-button>
        <el-button type="primary" :disabled="!activeCandidate" @click="openVersionDialog">
          创建改造版本
        </el-button>
        <el-button :disabled="!activeCandidate || !parentChoices.length" @click="openImportDialog">
          批量导入
        </el-button>
      </div>
    </section>

    <el-empty v-if="!candidates.length && !loading" description="请先添加候选抗体和 WT" />

    <template v-else-if="activeCandidate">
      <div class="studio">
      <section class="page-card lineage-card">
        <div class="section-head">
          <div>
            <h2>版本谱系</h2>
            <p>
              <el-tag size="small">{{ activeCandidate.antibody_category || '待分类' }}</el-tag>
              · {{ activeCandidate.candidate_code }}
              · {{ activeCandidate.antibody_type.toUpperCase() }}
            </p>
          </div>
          <div class="candidate-actions">
          <el-button
            type="primary"
            plain
            :disabled="!versions.length"
            :loading="folding"
            @click="submitFold()"
          >
            折叠本候选结构
          </el-button>
          <el-button
            v-if="allDraftCount"
            type="warning"
            plain
            @click="doLockDrafts(undefined, allDraftCount)"
          >
            锁定全部草稿（{{ allDraftCount }}）
          </el-button>
          </div>
        </div>
        <div class="lineage-tree">
          <section v-for="group in lineageGroups" :key="group.key" class="lineage-round">
            <div class="lineage-round-head">
              <h3>{{ group.label }}</h3>
              <el-button
                v-if="group.key !== 'WT' && group.draftCount"
                size="small"
                type="warning"
                plain
                @click="doLockDrafts(group.key, group.draftCount)"
              >
                锁定本轮草稿（{{ group.draftCount }}）
              </el-button>
            </div>
            <div class="version-grid">
              <button
                v-for="version in group.items"
                :key="version.id"
                type="button"
                class="version-node"
                :class="{ active: activeVersionId === version.id }"
                @click="activeVersionId = version.id"
              >
                <strong>{{ version.version_code }}</strong>
                <template v-if="versionNameParts(version.name).length">
                  <span v-for="(part, index) in versionNameParts(version.name)" :key="index">{{ part }}</span>
                </template>
                <span v-else class="version-note">无备注</span>
                <small class="status-pill" :data-status="version.status">{{ statusText[version.status] }}</small>
              </button>
            </div>
          </section>
        </div>
      </section>

      <section v-if="activeVersion" class="page-card structure-card">
        <div class="section-head">
          <div>
            <h2 class="version-title">
              {{ activeVersion.version_code }}
              <template v-if="activeVersion.name"> · {{ activeVersion.name }}</template>
            </h2>
            <p>
              父本 {{ parentVersion?.version_code || (activeVersion.primary_parent_id ? '未加载' : '无（本版为母本）') }}
              · 指纹 {{ activeVersion.sequence_hash.slice(0, 12) }}…
            </p>
          </div>
          <div class="candidate-actions">
            <el-button type="primary" plain :loading="folding" @click="submitFold([activeVersion.id])">
              折叠此版本
            </el-button>
            <el-button
              v-if="activeVersion.status === 'draft' && activeVersion.version_code.toUpperCase() !== 'WT'"
              type="danger"
              plain
              @click="doDelete"
            >
              删除序列
            </el-button>
            <el-button v-if="activeVersion.status === 'draft'" type="warning" plain @click="doLock">
              锁定版本
            </el-button>
          </div>
        </div>
        <VersionStructurePanel
          v-if="activeFoldJobId"
          :key="activeFoldJobId"
          :version="activeVersion"
          :parent-version="parentVersion"
          :job-id="activeFoldJobId"
          :parent-job-id="parentFoldJobId || null"
        />
        <p v-else class="empty-note">还没有抗体自身折叠。点「折叠此版本」或左侧「折叠本候选结构」，完成后会在这里看突变。</p>
      </section>

      <section class="page-card impact-card">
        <div class="section-head">
          <div>
            <h2>亲和力与理化</h2>
            <p>按版本号排在一起，每行对着父本看突变、KD 和已经测到的理化。父本低于检测限时，不再把倍数放大。</p>
          </div>
        </div>
        <ul v-if="patternNotes.length" class="pattern-notes">
          <li v-for="note in patternNotes" :key="note">{{ note }}</li>
        </ul>
        <div v-if="impactRows.length" class="table-wrap">
          <el-table
            :key="impactTableKey"
            :data="impactRows"
            size="small"
            highlight-current-row
            :current-row-key="activeVersionId"
            row-key="id"
            style="width: 100%"
            @row-click="selectImpactRow"
          >
            <el-table-column prop="version_code" label="版本" width="88" fixed />
            <el-table-column prop="parentCode" label="父本" width="72" />
            <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
            <el-table-column prop="mutations" label="相对父本突变" min-width="120" show-overflow-tooltip />
            <el-table-column
              v-for="antigen in impactAntigens"
              :key="antigen"
              :label="antigen"
              min-width="150"
            >
              <template #default="{ row }">
                <div class="impact-cell">
                  <strong>{{ row.byAntigen[antigen]?.kdText || '未测' }}</strong>
                  <small :class="`impact-${row.byAntigen[antigen]?.tone || 'na'}`">
                    {{ row.byAntigen[antigen]?.vsParent || '–' }}
                  </small>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="已测理化" min-width="180">
              <template #default="{ row }">
                <div v-if="measuredPhyschem(row).length" class="physchem-grid">
                  <div v-for="item in measuredPhyschem(row)" :key="item.key" class="physchem-item">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.text }}</strong>
                    <small :class="`impact-${item.tone}`">{{ item.vsParent }}</small>
                  </div>
                </div>
                <span v-else class="impact-na">未测</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <p v-else class="empty-note">当前候选还没有版本</p>
        <p v-if="impactRows.length && !impactAntigens.length" class="empty-note">
          还没有亲和力实验。导入后会按抗原分列显示 KD。
        </p>
      </section>

      <section v-if="activeVersion" class="page-card version-detail">
        <div class="chain-grid">
          <ChainSequencePair
            v-for="chain in activeVersion.chains"
            :key="chain.id"
            :chain="chain"
            :parent-chain="parentChainFor(chain)"
            :parent-label="versionDisplayName(parentVersion)"
            :child-label="versionDisplayName(activeVersion)"
            :mutations="activeVersion.mutations"
          />
        </div>

        <h3 class="mutation-title">相对父版本的突变</h3>
        <div v-if="activeVersion.mutations.length" class="table-wrap">
          <el-table :data="activeVersion.mutations" size="small" style="width: 100%">
            <el-table-column prop="chain_role" label="链" min-width="70" />
            <el-table-column label="类型" min-width="80">
              <template #default="{ row }">{{ mutationText[row.mutation_type] }}</template>
            </el-table-column>
            <el-table-column prop="sequence_position" label="顺序位点" min-width="95" />
            <el-table-column prop="kabat_label" label="Kabat" min-width="80" />
            <el-table-column label="变化" min-width="110">
              <template #default="{ row }">{{ row.from_aa || '–' }} → {{ row.to_aa || '–' }}</template>
            </el-table-column>
            <el-table-column prop="region" label="区域" min-width="95" />
          </el-table>
        </div>
        <p v-else class="empty-note">WT 或与父版本没有序列差异</p>

        <h3 class="mutation-title">该版本的亲和力实验</h3>
        <div v-if="activeVersionExperiments.length" class="table-wrap">
          <el-table :data="activeVersionExperiments" size="small" style="width: 100%">
            <el-table-column prop="antigen" label="抗原" min-width="140" />
            <el-table-column prop="result" label="结果" min-width="90" />
            <el-table-column prop="kd" label="KD" min-width="110" />
            <el-table-column prop="ka" label="ka" min-width="110" />
            <el-table-column prop="kdis" label="kdis" min-width="110" />
            <el-table-column prop="title" label="记录" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
        <p v-else class="empty-note">这个版本还没有亲和力实验。请到「样品与实验」导入。</p>

        <h3 class="mutation-title">该版本的理化</h3>
        <div v-if="activePhyschem" class="table-wrap">
          <el-table :data="activePhyschemRows" size="small" style="width: 100%">
            <el-table-column prop="label" label="指标" min-width="120" />
            <el-table-column prop="text" label="结果" min-width="140" />
            <el-table-column label="相对父本" min-width="120">
              <template #default="{ row }">
                <span :class="`impact-${row.tone}`">{{ row.vsParent }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <p v-else class="empty-note">这个版本还没有理化结果。请到「样品与实验」导入理化表格。</p>
      </section>
      </div>
    </template>

    <el-dialog v-model="showCandidate" title="添加候选抗体和 WT" width="700px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="候选编号"><el-input v-model="candidateForm.candidate_code" placeholder="AB-A" /></el-form-item>
          <el-form-item label="候选名称"><el-input v-model="candidateForm.name" /></el-form-item>
        </div>
        <el-form-item label="抗体分类（设置后不可修改）">
          <el-radio-group v-model="candidateForm.antibody_category">
            <el-radio value="RM">RM</el-radio>
            <el-radio value="RN">RN</el-radio>
            <el-radio value="RL">RL</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="抗体类型">
          <el-radio-group v-model="candidateForm.antibody_type">
            <el-radio value="igg">IgG</el-radio>
            <el-radio value="vhh">VHH</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="candidateForm.antibody_type === 'igg'">
          <el-form-item label="WT · VH 可变区"><el-input v-model="candidateForm.vh" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="WT · VL 可变区"><el-input v-model="candidateForm.vl" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="WT · 完整重链（可选）"><el-input v-model="candidateForm.full_vh" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="WT · 完整轻链（可选）"><el-input v-model="candidateForm.full_vl" type="textarea" :rows="2" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="WT · VHH 可变区"><el-input v-model="candidateForm.vhh" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="WT · 完整 VHH 链（可选）"><el-input v-model="candidateForm.full_vhh" type="textarea" :rows="2" /></el-form-item>
        </template>
        <el-form-item label="说明"><el-input v-model="candidateForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCandidate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCandidate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showCategory" title="设置固定抗体分类" width="420px">
      <el-alert
        title="RM/RN/RL 设置后不能修改，请确认选择正确。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-radio-group v-model="pendingCategory" class="category-options">
        <el-radio-button value="RM">RM</el-radio-button>
        <el-radio-button value="RN">RN</el-radio-button>
        <el-radio-button value="RL">RL</el-radio-button>
      </el-radio-group>
      <template #footer>
        <el-button @click="showCategory = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCategory">确认分类</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showVersion" title="创建改造版本" width="760px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="来源版本">
            <el-select v-model="versionForm.parent_version_id" style="width: 100%">
              <el-option v-for="item in parentChoices" :key="item.id" :label="item.version_code" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="备注（可选）">
            <el-input v-model="versionForm.name" placeholder="例如 clone_27，不要填写 M1" />
          </el-form-item>
        </div>
        <p class="empty-note">编号由系统生成，例如来源是 WT 时为 M1-001、M1-002。</p>
        <template v-if="activeCandidate?.antibody_type === 'igg'">
          <el-form-item label="VH 可变区"><el-input v-model="versionForm.vh" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="VL 可变区"><el-input v-model="versionForm.vl" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="完整重链（可选）"><el-input v-model="versionForm.full_vh" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="完整轻链（可选）"><el-input v-model="versionForm.full_vl" type="textarea" :rows="2" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="VHH 可变区"><el-input v-model="versionForm.vhh" type="textarea" :rows="4" /></el-form-item>
          <el-form-item label="完整 VHH 链（可选）"><el-input v-model="versionForm.full_vhh" type="textarea" :rows="2" /></el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showVersion = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitVersion">创建版本</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showImport" title="批量导入改造版本" width="760px">
      <el-form label-position="top">
        <el-form-item label="来源版本">
          <el-select v-model="importForm.parent_version_id" style="width: 100%">
            <el-option v-for="item in parentChoices" :key="item.id" :label="item.version_code" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="FASTA 或 Excel 表格">
          <el-upload
            v-model:file-list="importFileList"
            drag
            :auto-upload="false"
            :limit="1"
            accept=".fa,.fasta,.fas,.fna,.txt,.xlsx,.xlsm"
            :on-change="onFastaFileChange"
            :on-remove="onFastaFileRemove"
          >
            <div class="el-upload__text">将 FASTA 或 .xlsx 拖到此处，或 <em>点击选择文件</em></div>
          </el-upload>
        </el-form-item>
        <el-form-item label="也可以粘贴序列（没有文件时使用）">
          <el-input
            v-model="importForm.text"
            type="textarea"
            :rows="6"
            :placeholder="activeCandidate?.antibody_type === 'vhh'
              ? '>clone_27\\nEVQLVES...\\n>clone_28\\nEVQLVES...'
              : '>clone_27_VH\\nQVQLVQ...\\n>clone_27_VL\\nDIQMTQ...'"
          />
        </el-form-item>
        <p class="empty-note">
          Excel：单链用「蛋白名称」和「基因序列」。IgG 需要重链、轻链各一列序列（如 VH氨基酸序列、VL氨基酸序列），「克隆编号」只作备注。
          FASTA：每个 <code>&gt;</code> 标题对应一条版本；IgG 要用 <code>&gt;名称_VH</code> 和 <code>&gt;名称_VL</code> 成对。
          编号仍由系统生成，例如 M1-001。
        </p>
      </el-form>
      <template #footer>
        <el-button @click="showImport = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.version-workspace { display: grid; gap: 1rem; min-width: 0; }
.candidate-bar {
  padding: 0.85rem 1rem;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem 1rem;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(0, 172, 161, 0.06), transparent 70%),
    #fff;
}
.studio {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}
.lineage-card {
  grid-column: 1;
  grid-row: 1;
  align-self: start;
  max-height: calc(100vh - 150px);
  overflow: auto;
  border-radius: 16px;
}
.structure-card {
  grid-column: 2;
  grid-row: 1;
  align-self: start;
  border-radius: 16px;
}
.version-detail,
.impact-card {
  grid-column: 1 / -1;
  border-radius: 16px;
}
.candidate-picker {
  flex: 1 1 280px;
  min-width: 0;
  max-width: 560px;

  :deep(.el-select) { width: 100%; }
}
.field-label { display: block; margin-bottom: 0.3rem; color: var(--muted); font-size: 0.74rem; }
.candidate-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.55rem;
}
.lineage-card, .structure-card, .version-detail, .impact-card { padding: 1rem; min-width: 0; }
.lineage-card {
  .section-head,
  .candidate-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .candidate-actions { justify-content: flex-start; }
  .el-button { margin: 0; }
}
.pattern-notes {
  margin: 0 0 0.8rem;
  padding-left: 1.1rem;
  color: var(--body);
  font-size: 0.82rem;
  line-height: 1.55;
}
.physchem-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.28rem 0.7rem;
}
.physchem-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: 0.35rem;
  align-items: baseline;
  line-height: 1.25;
  span { color: var(--muted); font-size: 0.72rem; }
  strong { font-size: 0.78rem; }
  small { grid-column: 2; font-size: 0.68rem; }
}
.impact-cell {
  display: grid;
  gap: 0.12rem;
  line-height: 1.25;
  strong { font-size: 0.82rem; }
  small { font-size: 0.72rem; }
}
.impact-better { color: #157a3a; font-weight: 700; }
.impact-worse { color: #c0392b; font-weight: 700; }
.impact-same { color: var(--muted); }
.impact-na { color: var(--muted); }
.lineage-tree { display: grid; gap: 1.1rem; min-width: 0; }
.lineage-round-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.55rem;
}
.lineage-round h3 {
  margin: 0;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
}
.version-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.45rem;
}
.version-node {
  min-width: 0;
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 0.28rem;
  overflow: visible;

  &.active {
    border-color: var(--bio-green);
    background: var(--bio-green-light);
    box-shadow: inset 3px 0 0 var(--bio-green-dark);
  }
  strong { color: var(--title); font-size: 0.92rem; }
  span {
    font-size: 0.76rem;
    color: var(--body);
    overflow-wrap: anywhere;
    word-break: break-word;
    white-space: normal;
    line-height: 1.4;
  }
  .version-note { color: var(--muted); }
  .status-pill { justify-self: start; margin-top: 0.15rem; }
}
.version-title {
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: 1.4;
}
.chain-grid { display: grid; gap: 0.8rem; min-width: 0; }
.mutation-title { margin: 1.2rem 0 0.65rem; font-size: 0.95rem; color: var(--title); }
.category-options { display: flex; justify-content: center; margin-top: 1rem; }

@media (max-width: 960px) {
  .studio { grid-template-columns: minmax(0, 1fr); }
  .lineage-card,
  .structure-card,
  .version-detail,
  .impact-card {
    grid-column: 1;
    grid-row: auto;
    position: static;
    max-height: none;
  }
}
@media (max-width: 720px) {
  .candidate-bar { align-items: stretch; flex-direction: column; }
  .candidate-picker { max-width: none; }
  .candidate-actions { justify-content: flex-start; }
}
</style>
