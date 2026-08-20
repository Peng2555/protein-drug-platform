<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteBatch, exportBatchCsv } from '@/api/batches'
import { useBatchDetailStore, useFoldTasksStore } from '@/stores/foldTasks'
import { BATCH_JOBS_PAGE_SIZE, batchStatusLabel, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const batchStore = useBatchDetailStore()
const foldStore = useFoldTasksStore()

const batchId = computed(() => route.params.id as string)

const progressPct = computed(() => {
  const b = batchStore.batch
  if (!b?.heavy_chain_count) return 0
  return Math.round((b.done_count / b.heavy_chain_count) * 100)
})

const totalPages = computed(() =>
  Math.ceil(batchStore.batchJobsTotal / BATCH_JOBS_PAGE_SIZE),
)

async function load() {
  await batchStore.loadBatch(batchId.value)
}

function openJob(jobId: string) {
  router.push({
    name: 'fold-task',
    params: { id: jobId },
    query: { batch: batchId.value },
  })
}

async function changePage(page: number) {
  if (page < 0 || page >= totalPages.value) return
  await batchStore.loadBatchJobsPage(batchId.value, page)
}

async function onDelete() {
  const b = batchStore.batch
  if (!b) return
  try {
    await ElMessageBox.confirm(`确定删除批次「${b.name}」吗？此操作不可恢复。`, '删除批次', {
      type: 'warning',
    })
    await deleteBatch(b.id)
    batchStore.reset()
    await foldStore.refreshFoldTasks()
    router.push({ name: 'fold-tasks' })
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function onExport() {
  const b = batchStore.batch
  if (!b) return
  void exportBatchCsv(b.id, b.name)
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'running' || status === 'partial') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

watch(batchId, () => void load())

onMounted(() => {
  void load()
  foldStore.startPolling(async () => {
    if (batchStore.batch) {
      await batchStore.refreshBatch(batchId.value)
    }
  })
})

onUnmounted(() => {
  batchStore.reset()
})
</script>

<template>
  <div v-loading="batchStore.loading" class="detail-panel page-card page-card--accent">
    <template v-if="batchStore.batch">
      <div class="detail-head">
        <div class="detail-title-block">
          <h2>{{ batchStore.batch.name }}</h2>
          <p class="detail-meta">
            靶点 {{ batchStore.batch.target_name }}（{{ batchStore.batch.target_chain_id }}，{{
              batchStore.batch.target_sequence.length
            }}
            aa）· 重链链 ID {{ batchStore.batch.heavy_chain_id }} · 提交于
            {{ new Date(batchStore.batch.created_at).toLocaleString('zh-CN') }}
          </p>
        </div>
        <div class="detail-actions">
          <el-tag
            :type="statusTagType(batchStore.batch.status === 'partial' ? 'running' : batchStore.batch.status)"
            size="small"
          >
            {{ batchStatusLabel(batchStore.batch.status) }}
          </el-tag>
          <el-button size="small" @click="onExport">导出 CSV</el-button>
          <el-button size="small" type="danger" plain @click="onDelete">删除批次</el-button>
        </div>
      </div>

      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: `${progressPct}%` }" />
      </div>
      <p class="detail-meta">
        进度 {{ batchStore.batch.done_count }}/{{ batchStore.batch.heavy_chain_count }} 完成 · 运行
        {{ batchStore.batch.running_count }} · 排队 {{ batchStore.batch.queued_count }} · 失败
        {{ batchStore.batch.failed_count }}
      </p>

      <div class="batch-jobs-table">
        <el-table :data="batchStore.batchJobs" stripe @row-click="(row) => openJob(row.id)">
          <el-table-column label="重链 ID" min-width="120">
            <template #default="{ row }">
              <strong>{{ row.heavy_chain_id || row.name || '—' }}</strong>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="ipTM" width="90">
            <template #default="{ row }">{{ row.iptm?.toFixed(3) ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="pDockQ" width="90">
            <template #default="{ row }">{{ row.pdockq?.toFixed(3) ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="pLDDT" width="90">
            <template #default="{ row }">{{ row.complex_plddt?.toFixed(3) ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" @click.stop="openJob(row.id)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="batchStore.batchJobsTotal > BATCH_JOBS_PAGE_SIZE" class="batch-pager">
          <el-button
            size="small"
            :disabled="batchStore.batchJobsPage <= 0"
            @click="changePage(batchStore.batchJobsPage - 1)"
          >
            上一页
          </el-button>
          <span class="pager-info">
            第 {{ batchStore.batchJobsPage + 1 }}/{{ totalPages }} 页 ·
            {{ batchStore.batchJobsPage * BATCH_JOBS_PAGE_SIZE + 1 }}–{{
              Math.min((batchStore.batchJobsPage + 1) * BATCH_JOBS_PAGE_SIZE, batchStore.batchJobsTotal)
            }}
            / {{ batchStore.batchJobsTotal }}
          </span>
          <el-button
            size="small"
            :disabled="batchStore.batchJobsPage >= totalPages - 1"
            @click="changePage(batchStore.batchJobsPage + 1)"
          >
            下一页
          </el-button>
        </div>
      </div>
    </template>
    <el-empty v-else description="批次不存在" />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';

.batch-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.pager-info {
  font-size: 0.78rem;
  color: var(--muted);
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
