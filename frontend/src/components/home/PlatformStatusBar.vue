<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { fetchPlatformHealth, type PlatformHealth } from '@/api/health'

const health = ref<PlatformHealth | null>(null)
const loading = ref(true)
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  try {
    health.value = await fetchPlatformHealth()
  } catch {
    health.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  timer = setInterval(() => void load(), 30_000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div v-loading="loading" class="status-bar">
    <div class="status-bar__item">
      <span class="status-bar__label">GPU Worker</span>
      <strong>{{ health?.gpu_workers ?? '—' }}</strong>
    </div>
    <div class="status-bar__sep" />
    <div class="status-bar__item">
      <span class="status-bar__label">队列待跑</span>
      <strong>{{ health?.queue_depth ?? '—' }}</strong>
    </div>
    <div class="status-bar__sep" />
    <div class="status-bar__item">
      <span class="status-bar__label">运行中任务</span>
      <strong>{{ health?.running_jobs ?? '—' }}</strong>
    </div>
    <div class="status-bar__sep" />
    <div class="status-bar__item">
      <span class="status-bar__label">服务状态</span>
      <el-tag
        size="small"
        :type="health?.status === 'ok' ? 'success' : health ? 'warning' : 'info'"
        effect="plain"
      >
        {{ health?.status === 'ok' ? '正常' : health?.status ?? '未知' }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped lang="scss">
.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.85rem;
  padding: 0.65rem 0.9rem;
  border-radius: 12px;
  border: 1px solid rgba(0, 172, 161, 0.18);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(6px);
  min-height: 44px;
}

.status-bar__item {
  display: flex;
  align-items: center;
  gap: 0.45rem;

  strong {
    font-size: 0.92rem;
    color: var(--title);
    font-variant-numeric: tabular-nums;
  }
}

.status-bar__label {
  font-size: 0.72rem;
  color: var(--muted);
}

.status-bar__sep {
  width: 1px;
  height: 18px;
  background: var(--border);
  flex-shrink: 0;

  @media (max-width: 640px) {
    display: none;
  }
}
</style>
