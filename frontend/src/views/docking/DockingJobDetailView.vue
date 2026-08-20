<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteDockingJob, downloadDockingFile, fetchDockingJob } from '@/api/docking'
import type { DockingJob } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()

const job = ref<DockingJob | null>(null)
const showRaw = ref(false)
const jobId = computed(() => route.params.id as string)
const ligandSmiles = computed(() => String(job.value?.params_json?.ligand_smiles ?? ''))
const engineName = computed(() => String(job.value?.params_json?.engine ?? ''))
const dockMode = computed(() =>
  String(job.value?.results_json?.dock_mode ?? job.value?.params_json?.dock_mode ?? ''),
)
const sampling = computed(
  () => (job.value?.results_json?.sampling ?? null) as Record<string, unknown> | null,
)
const poses = computed(
  () => (job.value?.results_json?.poses as Record<string, unknown>[] | undefined) ?? [],
)
const cavityRanking = computed(
  () =>
    (job.value?.results_json?.cavity_ranking as Record<string, unknown>[] | undefined) ?? [],
)
const cavities = computed(
  () => (job.value?.results_json?.cavities as Record<string, unknown>[] | undefined) ?? [],
)
const bestPose = computed(
  () => (job.value?.results_json?.best_pose as Record<string, unknown> | undefined) ?? null,
)
const outputFiles = computed(
  () => (job.value?.results_json?.output_files as string[] | undefined) ?? [],
)
const modeLabel = computed(() => {
  if (dockMode.value === 'auto_blind') return '自动盲对接'
  if (dockMode.value === 'reference') return '参考配体定口袋'
  if (dockMode.value === 'manual') return '手动搜索盒'
  return '分子对接'
})

let timer: ReturnType<typeof setInterval> | null = null

async function load() {
  try {
    job.value = await fetchDockingJob(jobId.value)
  } catch (e) {
    job.value = null
    ElMessage.error(e instanceof Error ? e.message : '加载失败')
  }
}

function poll() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) {
    timer = setInterval(() => void load(), 5000)
  }
}

async function onDelete() {
  const j = job.value
  if (!j) return
  try {
    await ElMessageBox.confirm(
      `确定删除「${j.name || j.id.slice(0, 8)}」吗？此操作不可恢复。`,
      '删除任务',
      { type: 'warning' },
    )
    await deleteDockingJob(j.id)
    await moduleJobs.refreshDocking()
    router.push({ name: 'docking-tasks' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

async function download(filename: string) {
  try {
    await downloadDockingFile(job.value!.id, filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

function fmt(v: unknown, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

watch(() => job.value?.status, poll)
watch(jobId, () => void load())

onMounted(async () => {
  await load()
  poll()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div>
        <h2>{{ job.name || job.id }}</h2>
        <p>{{ modeLabel }} · {{ engineName || 'vina' }} · 口袋引导对接</p>
      </div>
      <div class="detail-actions">
        <el-tag>{{ statusLabel(job.status) }}</el-tag>
        <el-button size="small" @click="load">刷新</el-button>
        <el-button size="small" type="danger" plain @click="onDelete">删除</el-button>
      </div>
    </div>

    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />

    <div class="meta-row">
      <div>
        <span>阶段</span>
        <strong>{{ job.stage || 'queued' }}</strong>
      </div>
      <div>
        <span>耗时</span>
        <strong>{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</strong>
      </div>
      <div>
        <span>最优亲和力</span>
        <strong>
          {{
            bestPose?.affinity_kcal_mol != null
              ? `${fmt(bestPose.affinity_kcal_mol)} kcal/mol`
              : '—'
          }}
        </strong>
      </div>
      <div>
        <span>最优口袋</span>
        <strong>{{ bestPose?.cavity_id != null ? `Cavity ${bestPose.cavity_id}` : '—' }}</strong>
      </div>
    </div>

    <p v-if="ligandSmiles" class="smiles-line">
      SMILES：<code>{{ ligandSmiles }}</code>
    </p>

    <template v-if="job.status === 'done' && job.results_json">
      <el-alert
        v-if="job.results_json.complex_pdb"
        type="success"
        :closable="false"
        title="已生成全局最佳 Pose 的受体–配体复合物，可在下方下载结构文件。"
        class="complex-alert"
      />
      <p v-if="sampling?.note" class="field-hint">
        {{ sampling.note }}
        采样 {{ sampling.generated_conformers }} 个构象，使用 {{ sampling.used_starts }} 个独立起点。
      </p>

      <template v-if="cavityRanking.length">
        <h4>口袋排序（按最佳亲和力）</h4>
        <el-table :data="cavityRanking" size="small" border stripe>
          <el-table-column prop="cavity_id" label="口袋" width="80" />
          <el-table-column label="体积 (Å³)" width="110">
            <template #default="{ row }">{{ row.volume != null ? fmt(row.volume, 1) : '—' }}</template>
          </el-table-column>
          <el-table-column label="中心 (x,y,z)" min-width="180">
            <template #default="{ row }">
              {{ fmt(row.center_x) }}, {{ fmt(row.center_y) }}, {{ fmt(row.center_z) }}
            </template>
          </el-table-column>
          <el-table-column label="盒尺寸" min-width="150">
            <template #default="{ row }">
              {{ fmt(row.size_x, 1) }} × {{ fmt(row.size_y, 1) }} × {{ fmt(row.size_z, 1) }}
            </template>
          </el-table-column>
          <el-table-column label="最佳亲和力" width="120">
            <template #default="{ row }">{{ fmt(row.best_affinity_kcal_mol) }}</template>
          </el-table-column>
          <el-table-column prop="n_poses" label="Poses" width="80" />
        </el-table>
      </template>

      <template v-else-if="cavities.length">
        <h4>检测到的口袋</h4>
        <el-table :data="cavities" size="small" border>
          <el-table-column prop="cavity_id" label="口袋" width="80" />
          <el-table-column label="体积 (Å³)" width="110">
            <template #default="{ row }">{{ row.volume != null ? fmt(row.volume, 1) : '—' }}</template>
          </el-table-column>
          <el-table-column label="中心" min-width="180">
            <template #default="{ row }">
              {{ fmt(row.center_x) }}, {{ fmt(row.center_y) }}, {{ fmt(row.center_z) }}
            </template>
          </el-table-column>
        </el-table>
      </template>

      <h4>对接姿态（kcal/mol，全局排序）</h4>
      <el-table v-if="poses.length" :data="poses" size="small" border max-height="420">
        <el-table-column prop="pose" label="排名" width="70" />
        <el-table-column prop="cavity_id" label="口袋" width="70" />
        <el-table-column prop="start_seed" label="起点" width="70" />
        <el-table-column prop="vina_model" label="Model" width="80" />
        <el-table-column label="亲和力" width="100">
          <template #default="{ row }">{{ fmt(row.affinity_kcal_mol) }}</template>
        </el-table-column>
        <el-table-column label="RMSD lb" width="90">
          <template #default="{ row }">{{ fmt(row.rmsd_lb) }}</template>
        </el-table-column>
        <el-table-column label="RMSD ub" width="90">
          <template #default="{ row }">{{ fmt(row.rmsd_ub) }}</template>
        </el-table-column>
      </el-table>

      <div class="file-actions">
        <span>结果文件：</span>
        <el-button
          v-for="file in outputFiles.filter((f) =>
            ['docked_complex.pdb', 'docked_poses.pdbqt', 'summary.json', 'cavities.json'].includes(f),
          )"
          :key="file"
          size="small"
          type="primary"
          plain
          @click="download(file)"
        >
          {{ file }}
        </el-button>
        <el-button
          v-for="file in outputFiles.filter(
            (f) =>
              !['docked_complex.pdb', 'docked_poses.pdbqt', 'summary.json', 'cavities.json'].includes(
                f,
              ),
          )"
          :key="file"
          size="small"
          @click="download(file)"
        >
          {{ file }}
        </el-button>
      </div>
    </template>

    <button type="button" class="raw-toggle" @click="showRaw = !showRaw">
      {{ showRaw ? '收起运行摘要' : '查看完整 JSON 摘要' }}
    </button>
    <pre v-if="showRaw" class="result-box">{{
      JSON.stringify(job.results_json || { message: '任务运行中…' }, null, 2)
    }}</pre>
  </div>
  <el-empty v-else description="任务不存在或正在加载" />
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.detail-panel {
  padding: 1.5rem;
  max-width: 1100px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.detail-head h2 {
  margin: 0 0 0.35rem;
}
.detail-head p {
  color: var(--text-muted);
  margin: 0;
}
.detail-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}
.meta-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 1rem 0;
}
.meta-row > div {
  padding: 0.7rem 0.8rem;
  border-radius: 10px;
  background: rgba(0, 172, 161, 0.06);
  border: 1px solid rgba(0, 172, 161, 0.14);
}
.meta-row span {
  display: block;
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.2rem;
}
.meta-row strong {
  font-size: 0.95rem;
}
.smiles-line {
  word-break: break-all;
}
.smiles-line code {
  font-size: 0.85rem;
}
.result-box {
  max-height: 420px;
  overflow: auto;
  padding: 1rem;
  background: #111827;
  color: #d1fae5;
  border-radius: 6px;
  font-size: 0.78rem;
}
.file-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 1rem 0;
}
.complex-alert {
  margin: 1rem 0;
}
.field-hint {
  color: var(--text-muted);
  font-size: 0.85rem;
}
.raw-toggle {
  border: none;
  background: transparent;
  color: var(--bio-blue);
  cursor: pointer;
  padding: 0;
  margin-top: 0.5rem;
  font-size: 0.88rem;
}
h4 {
  margin: 1.1rem 0 0.55rem;
}
@media (max-width: 800px) {
  .meta-row {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
