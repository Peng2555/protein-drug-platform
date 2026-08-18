<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchRasDockingJob } from '@/api/rasDocking'
import type { RasDockingJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const job = ref<RasDockingJob | null>(null)
let timer: ReturnType<typeof setInterval> | null = null
async function load() {
  try { job.value = await fetchRasDockingJob(route.params.id as string) }
  catch (e) { ElMessage.error(e instanceof Error ? e.message : '加载失败') }
}
function startPolling() {
  if (timer) clearInterval(timer)
  if (job.value && ['queued', 'running'].includes(job.value.status)) timer = setInterval(() => void load(), 5000)
}
watch(() => job.value?.status, startPolling)
watch(() => route.params.id, () => void load())
onMounted(async () => { await load(); startPolling() })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div v-if="job" class="page-card page-card--accent detail-panel">
    <div class="detail-head">
      <div><h2>{{ job.name || job.id }}</h2><p>{{ job.params_json?.project }} · {{ job.params_json?.stage }}</p></div>
      <el-tag :type="job.status === 'done' ? 'success' : job.status === 'failed' ? 'danger' : 'warning'">{{ statusLabel(job.status) }}</el-tag>
    </div>
    <el-alert v-if="job.error_message" type="error" :closable="false" :title="job.error_message" />
    <el-descriptions :column="2" border class="meta">
      <el-descriptions-item label="当前阶段">{{ job.stage || 'queued' }}</el-descriptions-item>
      <el-descriptions-item label="耗时">{{ job.runtime_seconds ? `${Math.round(job.runtime_seconds)} 秒` : '—' }}</el-descriptions-item>
      <el-descriptions-item label="项目">{{ job.params_json?.project }}</el-descriptions-item>
      <el-descriptions-item label="输出文件">{{ (job.results_json?.output_files as string[] | undefined)?.length || 0 }}</el-descriptions-item>
    </el-descriptions>
    <h4>结果摘要</h4>
    <pre class="result-box">{{ JSON.stringify(job.results_json || { message: '任务运行中，结果将在完成后显示' }, null, 2) }}</pre>
  </div>
  <el-empty v-else description="任务不存在或正在加载" />
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.detail-panel { padding: 1.5rem; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; }
.detail-head h2 { margin: 0 0 .35rem; }
.detail-head p { color: var(--text-muted); }
.meta { margin: 1.25rem 0; }
.result-box { max-height: 600px; overflow: auto; padding: 1rem; background: #111827; color: #d1fae5; border-radius: 6px; font-size: .78rem; }
</style>
