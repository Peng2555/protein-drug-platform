<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { statusLabel } from '@/utils/constants'

const props = defineProps<{
  title: string
  subtitle: string
  kindLabel: string
  taskRouteName: string
  newRouteName: string
  jobs: Array<{ id: string; name?: string | null; status: string; created_at: string; meta?: string }>
  loading?: boolean
}>()

const emit = defineEmits<{
  refresh: []
  delete: [id: string]
}>()

const route = useRoute()
const router = useRouter()

const activeId = computed(() =>
  route.name === props.taskRouteName ? (route.params.id as string) : null,
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

function open(id: string) {
  router.push({ name: props.taskRouteName, params: { id } })
}

async function onDelete(id: string, name: string) {
  try {
    await ElMessageBox.confirm(`确定删除「${name}」吗？此操作不可恢复。`, '删除任务', {
      type: 'warning',
    })
    emit('delete', id)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

onMounted(() => emit('refresh'))
</script>

<template>
  <div class="module-tasks page-card">
    <header class="module-tasks__head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ subtitle }}</p>
      </div>
      <div class="module-tasks__actions">
        <el-button text :loading="loading" @click="emit('refresh')">刷新</el-button>
        <el-button type="primary" @click="router.push({ name: newRouteName })">新建任务</el-button>
      </div>
    </header>

    <div v-if="!jobs.length" class="empty-state">暂无任务，请先新建</div>
    <div v-else class="task-table">
      <div
        v-for="job in jobs"
        :key="job.id"
        class="task-row"
        :class="{ active: activeId === job.id }"
        @click="open(job.id)"
      >
        <div class="task-row__main">
          <span class="kind-badge">{{ kindLabel }}</span>
          <strong>{{ job.name || job.id.slice(0, 8) }}</strong>
          <el-tag :type="statusTagType(job.status)" size="small" effect="light">
            {{ statusLabel(job.status) }}
          </el-tag>
        </div>
        <div class="task-row__meta">
          <template v-if="job.meta">{{ job.meta }} · </template>
          {{ formatTime(job.created_at) }}
        </div>
        <button
          type="button"
          class="task-row__del"
          title="删除"
          @click.stop="onDelete(job.id, job.name || job.id.slice(0, 8))"
        >
          ×
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.module-tasks {
  padding: 1.15rem 1.25rem 1.4rem;
}

.module-tasks__head {
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

.module-tasks__actions {
  display: flex;
  gap: 0.45rem;
  flex-shrink: 0;
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
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
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

  &:hover {
    background: #fef2f2;
    color: #dc2626;
  }
}
</style>
