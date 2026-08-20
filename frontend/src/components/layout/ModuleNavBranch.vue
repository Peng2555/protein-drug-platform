<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowRight, Clock, Plus } from '@element-plus/icons-vue'
import type { Component } from 'vue'
import { statusLabel } from '@/utils/constants'
import type { ModuleNavItem } from '@/stores/moduleJobs'

const props = defineProps<{
  moduleId: string
  label: string
  icon: Component
  badge: number
  expanded: boolean
  recentItems: ModuleNavItem[]
  newRouteName: string
  tasksRouteName: string
  taskRouteName: string
  active: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

const route = useRoute()
const router = useRouter()

const onNew = computed(() => route.name === props.newRouteName)
const onTasks = computed(() => route.name === props.tasksRouteName)
const activeTaskId = computed(() =>
  route.name === props.taskRouteName ? (route.params.id as string) : null,
)

function statusTone(status: string) {
  if (status === 'done') return 'ok'
  if (status === 'running' || status === 'partial' || status === 'queued') return 'run'
  if (status === 'failed') return 'fail'
  return 'muted'
}

function formatShortTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function openNew() {
  router.push({ name: props.newRouteName })
}

function openTasks() {
  router.push({ name: props.tasksRouteName })
}

function openTask(id: string) {
  router.push({ name: props.taskRouteName, params: { id } })
}
</script>

<template>
  <div class="mod-branch" :class="{ open: expanded, active }">
    <button
      type="button"
      class="nav-item nav-item--mod"
      :class="{ active }"
      :title="label"
      @click="emit('toggle')"
    >
      <el-icon class="nav-icon" :size="18"><component :is="icon" /></el-icon>
      <span class="nav-label">{{ label }}</span>
      <span v-if="badge > 0" class="nav-badge" :class="{ 'is-active': active }">
        {{ badge > 99 ? '99+' : badge }}
      </span>
      <el-icon class="nav-chevron" :size="14">
        <ArrowDown v-if="expanded" />
        <ArrowRight v-else />
      </el-icon>
    </button>

    <div v-show="expanded" class="mod-submenu">
      <button
        type="button"
        class="mod-link mod-link--new"
        :class="{ active: onNew }"
        @click="openNew"
      >
        <el-icon :size="14"><Plus /></el-icon>
        新建任务
      </button>

      <div class="mod-recent-head">
        <el-icon :size="12"><Clock /></el-icon>
        最近任务
      </div>

      <div class="mod-recent-list">
        <button
          v-for="item in recentItems"
          :key="item.id"
          type="button"
          class="mod-task"
          :class="{ active: activeTaskId === item.id }"
          @click="openTask(item.id)"
        >
          <span class="mod-task__dot" :class="`is-${statusTone(item.status)}`" />
          <span class="mod-task__kind">{{ item.kindLabel }}</span>
          <span class="mod-task__name">{{ item.name }}</span>
          <span class="mod-task__status" :class="`is-${statusTone(item.status)}`">
            {{ statusLabel(item.status) }}
          </span>
          <span class="mod-task__time">{{ formatShortTime(item.created_at) }}</span>
        </button>
        <p v-if="!recentItems.length" class="mod-recent-empty">暂无任务</p>
      </div>

      <button
        type="button"
        class="mod-link mod-link--all"
        :class="{ active: onTasks }"
        @click="openTasks"
      >
        查看全部任务 →
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.mod-branch {
  border-radius: 12px;
  padding: 0.1rem;

  &.open,
  &.active {
    background: rgba(0, 172, 161, 0.06);
    border: 1px solid rgba(0, 172, 161, 0.2);
  }
}

.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.28rem;
  padding: 0.62rem 0.7rem;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--body);
  text-align: left;
  cursor: pointer;

  &:hover {
    background: var(--bio-green-light);
    color: var(--bio-green-dark);
  }

  &.active {
    background: linear-gradient(90deg, rgba(0, 172, 161, 0.14), rgba(46, 90, 165, 0.06));
    border-color: rgba(0, 172, 161, 0.35);
    color: var(--bio-green-darkest);
    box-shadow: inset 3px 0 0 var(--bio-green);
  }
}

.nav-icon { flex-shrink: 0; }
.nav-label {
  flex: 1;
  min-width: 0;
  font-size: 0.88rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-badge {
  flex-shrink: 0;
  min-width: 1.35rem;
  height: 1.2rem;
  padding: 0 0.35rem;
  border-radius: 999px;
  background: var(--bio-blue-light);
  color: var(--bio-blue-dark);
  font-size: 0.66rem;
  font-weight: 700;
  line-height: 1.2rem;
  text-align: center;

  &.is-active {
    background: var(--bio-green);
    color: #fff;
  }
}
.nav-chevron {
  flex-shrink: 0;
  opacity: 0.55;
  color: var(--muted);
}

.mod-submenu {
  padding: 0.15rem 0.4rem 0.55rem 0.55rem;
}

.mod-link {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  border: none;
  background: transparent;
  color: var(--body);
  padding: 0.4rem 0.45rem;
  border-radius: 8px;
  font-size: 0.78rem;
  cursor: pointer;
  text-align: left;

  &:hover,
  &.active {
    background: var(--bio-green-light);
    color: var(--bio-green-dark);
  }

  &--new {
    color: var(--bio-green-dark);
    font-weight: 700;
  }

  &--all {
    margin-top: 0.25rem;
    color: var(--bio-blue);
    font-weight: 600;
  }
}

.mod-recent-head {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0.45rem 0.35rem 0.3rem;
  font-size: 0.68rem;
  color: var(--muted);
  font-weight: 600;
}

.mod-recent-list {
  max-height: 320px;
  overflow-y: auto;
}

.mod-recent-empty {
  margin: 0.35rem 0.4rem;
  font-size: 0.72rem;
  color: var(--muted);
}

.mod-task {
  width: 100%;
  display: grid;
  grid-template-columns: 8px auto minmax(0, 1fr) auto;
  grid-template-rows: auto auto;
  column-gap: 0.35rem;
  row-gap: 0.08rem;
  align-items: center;
  margin-bottom: 0.22rem;
  padding: 0.4rem 0.4rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--body);
  cursor: pointer;
  text-align: left;

  &:hover,
  &.active {
    background: var(--bio-green-light);
    color: var(--bio-green-darkest);
  }
}

.mod-task__dot {
  grid-row: 1 / span 2;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;

  &.is-ok { background: var(--bio-green); }
  &.is-run { background: var(--warn); }
  &.is-fail { background: var(--err); }
}

.mod-task__kind {
  grid-column: 2;
  font-size: 0.58rem;
  font-weight: 700;
  padding: 0.02rem 0.28rem;
  border-radius: 3px;
  background: var(--bio-green-light);
  color: var(--bio-green-dark);
}

.mod-task__name {
  grid-column: 3;
  font-size: 0.74rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mod-task__status {
  grid-column: 4;
  font-size: 0.6rem;
  font-weight: 700;

  &.is-ok { color: var(--bio-green-dark); }
  &.is-run { color: #c67c00; }
  &.is-fail { color: var(--err); }
  &.is-muted { color: var(--muted); }
}

.mod-task__time {
  grid-column: 3 / span 2;
  font-size: 0.58rem;
  color: var(--muted);
}
</style>
