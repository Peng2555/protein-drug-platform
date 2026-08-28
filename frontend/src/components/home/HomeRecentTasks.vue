<script setup lang="ts">
import { statusLabel } from '@/utils/constants'

export interface RecentItem {
  id: string
  name: string
  status: string
  created_at: string
  kind: string
  routeName: string
  meta: string
}

defineProps<{
  items: RecentItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  open: [item: RecentItem]
  viewAll: []
}>()
</script>

<template>
  <div v-loading="loading" class="recent-block">
    <el-empty v-if="!loading && !items.length" description="暂无任务，从上方推荐工作流开始吧" />
    <div v-else class="recent-grid">
      <button
        v-for="item in items"
        :key="`${item.routeName}-${item.id}`"
        type="button"
        class="recent-card"
        @click="emit('open', item)"
      >
        <div class="recent-card__top">
          <el-tag size="small" effect="plain" type="info">{{ item.kind }}</el-tag>
          <el-tag
            size="small"
            :type="item.status === 'done' ? 'success' : item.status === 'failed' ? 'danger' : 'info'"
          >
            {{ statusLabel(item.status) }}
          </el-tag>
        </div>
        <strong>{{ item.name }}</strong>
        <span>{{ item.meta }}</span>
        <time>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</time>
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.recent-block {
  min-height: 120px;
}

.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.85rem;
}

.recent-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  padding: 1rem 1.05rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    transform 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.35);
    box-shadow: var(--shadow);
    transform: translateY(-2px);
  }

  strong {
    font-size: 0.92rem;
    color: var(--title);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }

  > span {
    font-size: 0.74rem;
    color: var(--muted);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  time {
    margin-top: 0.15rem;
    font-size: 0.68rem;
    color: var(--muted);
  }
}

.recent-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 0.5rem;
}
</style>
