<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteJob } from '@/api/jobs'
import { deleteBatch } from '@/api/batches'
import { useFoldTasksStore } from '@/stores/foldTasks'
import type { Batch, Job } from '@/api/types'
import { batchStatusLabel, engineLabel, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const store = useFoldTasksStore()

const activeJobId = computed(() =>
  route.name === 'fold-task' || route.name === 'fold-job' ? (route.params.id as string) : null,
)
const activeBatchId = computed(() =>
  route.name === 'fold-batch' ? (route.params.id as string) : null,
)

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

function openJob(job: Job) {
  router.push({ name: 'fold-task', params: { id: job.id } })
}

function openBatch(batch: Batch) {
  router.push({ name: 'fold-batch', params: { id: batch.id } })
}

async function onDeleteJob(job: Job) {
  const label = job.name || job.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${label}」吗？此操作不可恢复。`,
      '删除任务',
      { type: 'warning' },
    )
    await deleteJob(job.id)
    if (activeJobId.value === job.id) router.push({ name: 'fold-tasks' })
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
    if (activeBatchId.value === batch.id) router.push({ name: 'fold-tasks' })
    await store.refreshFoldTasks()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

onMounted(() => {
  void store.refreshFoldTasks()
  store.startPolling()
})
</script>

<template>
  <div class="fold-tasks page-card">
    <header class="fold-tasks__head">
      <div>
        <h1>全部任务</h1>
        <p>结构预测单条与 VHH 批次任务列表</p>
      </div>
      <div class="fold-tasks__actions">
        <el-button text :loading="store.loading" @click="store.refreshFoldTasks()">刷新</el-button>
        <el-button type="primary" @click="router.push({ name: 'fold-new' })">新建预测</el-button>
      </div>
    </header>

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

    <div v-if="!store.mergedTaskItems.length" class="empty-state">暂无任务，请先新建预测</div>
    <div v-else class="task-table">
      <div
        v-for="item in store.mergedTaskItems"
        :key="item.kind + item.data.id"
        class="task-row"
        :class="{
          active:
            (item.kind === 'single' && activeJobId === item.data.id) ||
            (item.kind === 'batch' && activeBatchId === item.data.id),
        }"
        @click="item.kind === 'single' ? openJob(item.data as Job) : openBatch(item.data as Batch)"
      >
        <div class="task-row__main">
          <span
            class="kind-badge"
            :class="item.kind === 'batch' ? 'kind-batch' : 'kind-single'"
          >
            {{ item.kind === 'batch' ? '批次' : '单条' }}
          </span>
          <strong>
            {{
              item.kind === 'single'
                ? (item.data as Job).name || item.data.id.slice(0, 8)
                : (item.data as Batch).name
            }}
          </strong>
          <el-tag :type="statusTagType(item.data.status)" size="small" effect="light">
            {{
              item.kind === 'batch'
                ? batchStatusLabel(item.data.status)
                : statusLabel(item.data.status)
            }}
          </el-tag>
        </div>
        <div class="task-row__meta">
          <template v-if="item.kind === 'single'">
            {{ Object.keys((item.data as Job).chains_json || {}).join(', ') || '—' }}
            · {{ (item.data as Job).total_length ?? '—' }} aa
            · {{ engineLabel((item.data as Job).engine) }}
            <template v-if="(item.data as Job).iptm != null">
              · ipTM {{ (item.data as Job).iptm!.toFixed(2) }}
            </template>
          </template>
          <template v-else>
            {{ (item.data as Batch).target_name }}
            · {{ (item.data as Batch).done_count }}/{{ (item.data as Batch).heavy_chain_count }} 完成
          </template>
          · {{ formatTime(item.data.created_at) }}
        </div>
        <button
          type="button"
          class="task-row__del"
          title="删除"
          @click.stop="
            item.kind === 'single'
              ? onDeleteJob(item.data as Job)
              : onDeleteBatch(item.data as Batch)
          "
        >
          ×
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.fold-tasks {
  padding: 1.15rem 1.25rem 1.4rem;
}

.fold-tasks__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;

  h1 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--title);
  }

  p {
    margin: 0.3rem 0 0;
    font-size: 0.84rem;
    color: var(--muted);
  }
}

.fold-tasks__actions {
  display: flex;
  gap: 0.45rem;
  flex-shrink: 0;
}

.task-filters {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}

.task-filter-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--muted);
  border-radius: 999px;
  padding: 0.28rem 0.75rem;
  font-size: 0.78rem;
  cursor: pointer;

  &.active {
    border-color: var(--bio-blue);
    color: var(--bio-blue-dark);
    background: var(--bio-blue-light);
    font-weight: 600;
  }
}

.empty-state {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: 0.88rem;
}

.task-row {
  position: relative;
  padding: 0.85rem 2.2rem 0.85rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 0.55rem;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;

  &:hover,
  &.active {
    border-color: rgba(37, 99, 235, 0.35);
    box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.12);
  }
}

.task-row__main {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-wrap: wrap;

  strong {
    color: var(--title);
    font-size: 0.92rem;
  }
}

.kind-badge {
  font-size: 0.66rem;
  font-weight: 700;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;

  &.kind-single {
    background: rgba(37, 99, 235, 0.12);
    color: #1d4ed8;
  }

  &.kind-batch {
    background: rgba(0, 172, 161, 0.14);
    color: var(--bio-green-dark);
  }
}

.task-row__meta {
  margin-top: 0.35rem;
  font-size: 0.76rem;
  color: var(--muted);
}

.task-row__del {
  position: absolute;
  top: 0.7rem;
  right: 0.7rem;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;

  &:hover {
    background: #fef2f2;
    color: #dc2626;
  }
}
</style>
