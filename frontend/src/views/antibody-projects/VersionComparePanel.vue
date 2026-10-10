<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  compareVersions,
  fetchCandidates,
  fetchVersions,
  type AntibodyCandidate,
  type AntibodyVersion,
  type VersionComparison,
} from '@/api/antibodyProjects'

const props = defineProps<{ projectId: string }>()
const candidates = ref<AntibodyCandidate[]>([])
const versions = ref<AntibodyVersion[]>([])
const candidateId = ref('')
const baseId = ref('')
const targetId = ref('')
const result = ref<VersionComparison | null>(null)
const loading = ref(false)

const baseVersion = computed(() => versions.value.find((item) => item.id === baseId.value))
const targetVersion = computed(() => versions.value.find((item) => item.id === targetId.value))

function chainSequence(version: AntibodyVersion | undefined, role: string) {
  return version?.chains.find((item) => item.chain_role === role)?.variable_sequence || ''
}

const chainRoles = computed(() =>
  Array.from(new Set([
    ...(baseVersion.value?.chains.map((item) => item.chain_role) || []),
    ...(targetVersion.value?.chains.map((item) => item.chain_role) || []),
  ])).sort(),
)

async function loadCandidates() {
  try {
    candidates.value = await fetchCandidates(props.projectId)
    candidateId.value ||= candidates.value[0]?.id || ''
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载失败')
  }
}

async function loadVersions() {
  result.value = null
  if (!candidateId.value) return
  versions.value = await fetchVersions(props.projectId, candidateId.value)
  baseId.value = versions.value[0]?.id || ''
  targetId.value = versions.value.at(-1)?.id || ''
}

async function compare() {
  if (!baseId.value || !targetId.value || baseId.value === targetId.value) {
    ElMessage.warning('请选择两个不同版本')
    return
  }
  loading.value = true
  try {
    result.value = await compareVersions(props.projectId, baseId.value, targetId.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '对比失败')
  } finally {
    loading.value = false
  }
}

watch(candidateId, () => void loadVersions())
onMounted(loadCandidates)
</script>

<template>
  <div class="compare-panel">
    <section class="page-card compare-controls">
      <div>
        <label>候选抗体</label>
        <el-select v-model="candidateId">
          <el-option
            v-for="candidate in candidates"
            :key="candidate.id"
            :label="`[${candidate.antibody_category || '待分类'}] ${candidate.candidate_code} · ${candidate.name}`"
            :value="candidate.id"
          />
        </el-select>
      </div>
      <div>
        <label>基准版本</label>
        <el-select v-model="baseId">
          <el-option v-for="version in versions" :key="version.id" :label="version.version_code" :value="version.id" />
        </el-select>
      </div>
      <div>
        <label>目标版本</label>
        <el-select v-model="targetId">
          <el-option v-for="version in versions" :key="version.id" :label="version.version_code" :value="version.id" />
        </el-select>
      </div>
      <el-button type="primary" :loading="loading" @click="compare">开始对比</el-button>
    </section>

    <template v-if="result">
      <section class="page-card compare-result">
        <div class="section-head">
          <div>
            <h2>{{ result.base_version.version_code }} 与 {{ result.target_version.version_code }}</h2>
            <p>共发现 {{ result.differences.length }} 个序列差异</p>
          </div>
        </div>
        <el-table :data="result.differences" size="small">
          <el-table-column prop="chain_role" label="链" width="80" />
          <el-table-column prop="sequence_position" label="顺序位点" width="110" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              {{ row.mutation_type === 'substitution' ? '替换' : row.mutation_type === 'insertion' ? '插入' : '删除' }}
            </template>
          </el-table-column>
          <el-table-column label="变化">
            <template #default="{ row }">
              <code>{{ row.from_aa || '–' }} → {{ row.to_aa || '–' }}</code>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section v-for="role in chainRoles" :key="role" class="page-card sequence-compare">
        <h3>{{ role }}</h3>
        <div class="sequence-columns">
          <div>
            <span>{{ result.base_version.version_code }}</span>
            <pre class="mono-sequence">{{ chainSequence(result.base_version, role) }}</pre>
          </div>
          <div>
            <span>{{ result.target_version.version_code }}</span>
            <pre class="mono-sequence">{{ chainSequence(result.target_version, role) }}</pre>
          </div>
        </div>
      </section>
    </template>
    <el-empty v-else description="选择同一候选抗体的两个版本进行对比" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.compare-panel { display: grid; gap: 1rem; }
.compare-controls {
  padding: 1rem;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  gap: 0.8rem;
  align-items: end;

  label { display: block; margin-bottom: 0.3rem; color: var(--muted); font-size: 0.72rem; }
  .el-select { width: 100%; }
}
.compare-result, .sequence-compare { padding: 1rem; }
.sequence-compare h3 { margin: 0 0 0.65rem; color: var(--title); }
.sequence-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0.8rem; }
.sequence-columns span { display: block; margin-bottom: 0.3rem; font-weight: 700; }

@media (max-width: 860px) {
  .compare-controls, .sequence-columns { grid-template-columns: 1fr; }
}
</style>
