<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadDockingFile, fetchDockingJob } from '@/api/docking'
import type { DockingJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'
const route = useRoute()
const job = ref<DockingJob | null>(null)
const ligandSmiles = computed(() => String(job.value?.params_json?.ligand_smiles ?? ''))
const engineName = computed(() => String(job.value?.params_json?.engine ?? ''))
const sampling = computed(() => (job.value?.results_json?.sampling ?? null) as Record<string, unknown> | null)
const poses = computed(() => (job.value?.results_json?.poses as Record<string, unknown>[] | undefined) ?? [])
const outputFiles = computed(() => (job.value?.results_json?.output_files as string[] | undefined) ?? [])
let timer: ReturnType<typeof setInterval> | null = null
async function load() {
  try { job.value = await fetchDockingJob(route.params.id as string) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '加载失败') }
}
function poll() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) timer = setInterval(() => void load(), 5000)
}
watch(() => job.value?.status, poll)
watch(() => route.params.id, () => void load())
onMounted(async () => { await load(); poll() })
onUnmounted(() => { if (timer) clearInterval(timer) })
async function download(filename: string) {
  try { await downloadDockingFile(job.value!.id, filename) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '下载失败') }
}
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div>
        <h2>{{ job.name || job.id }}</h2>
        <p>SMILES 采样起点 · 全局 Vina · {{ engineName }}</p>
      </div>
      <el-tag>{{ statusLabel(job.status) }}</el-tag>
    </div>
    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <p>当前阶段：{{ job.stage || 'queued' }} · 耗时：{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</p>
    <p v-if="ligandSmiles" class="smiles-line">
      SMILES：<code>{{ ligandSmiles }}</code>
    </p>
    <template v-if="job.status === 'done' && job.results_json">
      <el-alert
        v-if="job.results_json.complex_pdb"
        type="success"
        :closable="false"
        title="已生成全局最佳 Pose 的受体-配体复合物结构"
        class="complex-alert"
      />
      <p v-if="sampling?.note" class="field-hint">
        {{ sampling.note }}
        采样 {{ sampling.generated_conformers }} 个构象，
        使用 {{ sampling.used_starts }} 个独立起点。
      </p>
      <h4>对接评分（kcal/mol，按亲和力全局排序）</h4>
      <el-table v-if="poses.length" :data="poses" size="small" border>
        <el-table-column prop="pose" label="排名" width="70" />
        <el-table-column prop="start_seed" label="起点" width="70" />
        <el-table-column prop="vina_model" label="该起点 Model" width="110" />
        <el-table-column prop="affinity_kcal_mol" label="亲和力" />
        <el-table-column prop="rmsd_lb" label="相对起点 RMSD 下界" />
        <el-table-column prop="rmsd_ub" label="相对起点 RMSD 上界" />
      </el-table>
      <div class="file-actions">
        <span>结果文件：</span>
        <el-button
          v-for="file in outputFiles"
          :key="file"
          size="small"
          @click="download(file)"
        >
          下载 {{ file }}
        </el-button>
      </div>
    </template>
    <h4>运行摘要</h4>
    <pre class="result-box">{{ JSON.stringify(job.results_json || { message: '任务运行中…' }, null, 2) }}</pre>
  </div>
  <el-empty v-else description="任务不存在或正在加载" />
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.detail-panel { padding: 1.5rem; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; }
.detail-head h2 { margin: 0 0 .35rem; }
.detail-head p { color: var(--text-muted); }
.smiles-line { word-break: break-all; }
.smiles-line code { font-size: .85rem; }
.result-box { max-height: 650px; overflow: auto; padding: 1rem; background: #111827; color: #d1fae5; border-radius: 6px; font-size: .78rem; }
.file-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; margin: 1rem 0; }
.complex-alert { margin: 1rem 0; }
.field-hint { color: var(--text-muted); font-size: .85rem; }
</style>
