<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Aim,
  ArrowDown,
  ArrowRight,
  Clock,
  Cpu,
  DArrowLeft,
  DArrowRight,
  EditPen,
  Histogram,
  HomeFilled,
  MagicStick,
  Plus,
  Setting,
  Brush,
  DataAnalysis,
  Timer,
  UserFilled,
} from '@element-plus/icons-vue'
import ModuleNavBranch from '@/components/layout/ModuleNavBranch.vue'
import { useAuthStore } from '@/stores/auth'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { useModuleJobsStore, type ModuleJobKind, type ModuleNavItem } from '@/stores/moduleJobs'
import type { Batch, Job } from '@/api/types'
import {
  NAV_GROUPS,
  PLATFORM_NAME,
  PLATFORM_NAME_EN,
  PLATFORM_ORG,
  PLATFORM_TAGLINE,
  moduleIdFromPath,
  navItemById,
  type ModuleId,
} from '@/utils/platform'
import { batchStatusLabel, statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const foldStore = useFoldTasksStore()
const moduleJobs = useModuleJobsStore()
const collapsed = ref(false)

const expanded = reactive<Record<string, boolean>>({
  fold: true,
  design: false,
  rosetta: false,
  developability: false,
  maturation: false,
  synthesis: false,
  docking: false,
  md: false,
})

const activeModule = computed(() => moduleIdFromPath(route.path))
const currentNav = computed(() => navItemById(activeModule.value))
const onFold = computed(() => activeModule.value === 'fold')

const iconMap = {
  home: HomeFilled,
  fold: Cpu,
  design: Brush,
  rosetta: DataAnalysis,
  developability: EditPen,
  maturation: MagicStick,
  synthesis: Histogram,
  docking: Aim,
  md: Timer,
} as const

const expandableIds: ModuleId[] = [
  'fold',
  'design',
  'rosetta',
  'developability',
  'maturation',
  'synthesis',
  'docking',
  'md',
]

const badgeMap = computed(() => ({
  home: 0,
  fold: foldStore.foldTaskCount,
  design: moduleJobs.counts.design,
  rosetta: moduleJobs.counts.rosetta,
  developability: moduleJobs.counts.developability,
  maturation: moduleJobs.counts.maturation,
  synthesis: moduleJobs.counts.synthesis,
  docking: moduleJobs.counts.docking,
  md: moduleJobs.counts.md,
}) as Record<ModuleId, number>)

watch(
  activeModule,
  (id) => {
    if (expandableIds.includes(id)) expanded[id] = true
  },
  { immediate: true },
)

function moduleNewRoute(id: ModuleId) {
  return `${id}-new`
}

function toggleModule(id: ModuleId) {
  expanded[id] = !expanded[id]
  router.push({ name: moduleNewRoute(id) })
}

function goHome() {
  router.push({ name: 'home' })
}

function recentFor(id: ModuleId): Array<ModuleNavItem & { _kind?: 'single' | 'batch' }> {
  if (id === 'fold') {
    return foldStore.recentFoldItems.map((item) => ({
      id: item.data.id,
      name:
        item.kind === 'single'
          ? (item.data as Job).name || item.data.id.slice(0, 8)
          : (item.data as Batch).name,
      status: item.data.status,
      created_at: item.data.created_at,
      kindLabel: item.kind === 'batch' ? '批次' : '单条',
      _kind: item.kind as 'single' | 'batch',
    }))
  }
  return moduleJobs.recent(id as ModuleJobKind, 5)
}

/** fold 最近任务可能是 batch，需特殊打开 */
function openFoldRecent(item: { id: string; _kind?: 'single' | 'batch' }) {
  expanded.fold = true
  if (item._kind === 'batch') {
    router.push({ name: 'fold-batch', params: { id: item.id } })
  } else {
    router.push({ name: 'fold-task', params: { id: item.id } })
  }
}

const activeTaskId = computed(() => {
  if (route.name === 'fold-task' || route.name === 'fold-job') return route.params.id as string
  return null
})
const activeBatchId = computed(() =>
  route.name === 'fold-batch' ? (route.params.id as string) : null,
)
const onFoldNew = computed(() => route.name === 'fold-new')
const onFoldTasks = computed(() => route.name === 'fold-tasks')

function openFoldNew() {
  expanded.fold = true
  router.push({ name: 'fold-new' })
}
function openFoldTasks() {
  expanded.fold = true
  router.push({ name: 'fold-tasks' })
}
function isFoldRecentActive(item: { id: string; _kind?: 'single' | 'batch' }) {
  if (item._kind === 'batch') return activeBatchId.value === item.id
  return activeTaskId.value === item.id
}
function foldStatusTone(status: string) {
  if (status === 'done') return 'ok'
  if (status === 'running' || status === 'partial' || status === 'queued') return 'run'
  if (status === 'failed') return 'fail'
  return 'muted'
}
function foldStatusText(item: { status: string; _kind?: 'single' | 'batch' }) {
  return item._kind === 'batch' ? batchStatusLabel(item.status) : statusLabel(item.status)
}
function formatShortTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function crumbHint() {
  const name = String(route.name || '')
  if (name.endsWith('-new')) return '新建任务'
  if (name.endsWith('-tasks')) return '全部任务'
  if (name === 'fold-batch') return '批次详情'
  if (name.endsWith('-task') || name.endsWith('-job')) return '任务详情'
  return currentNav.value.hint
}

function onLogout() {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  void foldStore.refreshFoldTasks()
  void moduleJobs.refreshAll()
  foldStore.startPolling()
})
</script>

<template>
  <div class="layout-root" :class="{ 'is-collapsed': collapsed }">
    <aside class="app-sidebar" aria-label="功能模块">
      <RouterLink to="/home" class="sidebar-brand" :title="PLATFORM_NAME">
        <img src="/assets/biocytogen-logo.png" alt="百奥赛图" class="sidebar-logo" />
        <div v-show="!collapsed" class="sidebar-brand-text">
          <strong>{{ PLATFORM_NAME }}</strong>
          <span>{{ PLATFORM_NAME_EN }}</span>
        </div>
      </RouterLink>

      <nav class="sidebar-nav">
        <section class="nav-group">
          <p v-show="!collapsed" class="nav-group-label">工作台</p>
          <button
            type="button"
            class="nav-item"
            :class="{ active: activeModule === 'home' }"
            title="首页"
            @click="goHome"
          >
            <el-icon class="nav-icon" :size="18"><HomeFilled /></el-icon>
            <span v-show="!collapsed" class="nav-label">首页</span>
          </button>
        </section>

        <!-- 结构计算：fold 保留批次逻辑的自定义子菜单 -->
        <section class="nav-group">
          <p v-show="!collapsed" class="nav-group-label">结构计算</p>
          <div
            v-show="!collapsed"
            class="fold-branch"
            :class="{ open: expanded.fold, active: onFold }"
          >
            <button
              type="button"
              class="nav-item"
              :class="{ active: onFold }"
              title="结构预测"
              @click="toggleModule('fold')"
            >
              <el-icon class="nav-icon" :size="18"><Cpu /></el-icon>
              <span class="nav-label">结构预测</span>
              <span v-if="badgeMap.fold > 0" class="nav-badge" :class="{ 'is-active': onFold }">
                {{ badgeMap.fold > 99 ? '99+' : badgeMap.fold }}
              </span>
              <el-icon class="nav-chevron" :size="14">
                <ArrowDown v-if="expanded.fold" />
                <ArrowRight v-else />
              </el-icon>
            </button>

            <div v-show="expanded.fold" class="fold-submenu">
              <button
                type="button"
                class="fold-link fold-link--new"
                :class="{ active: onFoldNew }"
                @click="openFoldNew"
              >
                <el-icon :size="14"><Plus /></el-icon>
                新建预测
              </button>
              <div class="fold-recent-head">
                <el-icon :size="12"><Clock /></el-icon>
                最近任务
              </div>
              <div class="fold-recent-list">
                <button
                  v-for="item in recentFor('fold')"
                  :key="item.id"
                  type="button"
                  class="fold-task"
                  :class="{ active: isFoldRecentActive(item) }"
                  @click="openFoldRecent(item)"
                >
                  <span class="fold-task__dot" :class="`is-${foldStatusTone(item.status)}`" />
                  <span
                    class="fold-task__kind"
                    :class="item._kind === 'batch' ? 'kind-batch' : 'kind-single'"
                  >
                    {{ item.kindLabel }}
                  </span>
                  <span class="fold-task__name">{{ item.name }}</span>
                  <span class="fold-task__status" :class="`is-${foldStatusTone(item.status)}`">
                    {{ foldStatusText(item) }}
                  </span>
                  <span class="fold-task__time">{{ formatShortTime(item.created_at) }}</span>
                </button>
                <p v-if="!recentFor('fold').length" class="fold-recent-empty">暂无任务</p>
              </div>
              <button
                type="button"
                class="fold-link fold-link--all"
                :class="{ active: onFoldTasks }"
                @click="openFoldTasks"
              >
                查看全部任务 →
              </button>
            </div>
          </div>
          <button
            v-show="collapsed"
            type="button"
            class="nav-item"
            :class="{ active: onFold }"
            title="结构预测"
            @click="toggleModule('fold')"
          >
            <el-icon class="nav-icon" :size="18"><Cpu /></el-icon>
          </button>
        </section>

        <!-- 序列与抗体 / 小分子药物筛选：通用可展开分支 -->
        <section
          v-for="group in NAV_GROUPS.filter((g) => g.id === 'sequence' || g.id === 'ligand')"
          :key="group.id"
          class="nav-group"
        >
          <p v-show="!collapsed" class="nav-group-label">{{ group.label }}</p>
          <template v-for="item in group.items" :key="item.id">
            <ModuleNavBranch
              v-show="!collapsed"
              :module-id="item.id"
              :label="item.label"
              :icon="iconMap[item.id]"
              :badge="badgeMap[item.id]"
              :expanded="!!expanded[item.id]"
              :recent-items="recentFor(item.id)"
              :new-route-name="`${item.id}-new`"
              :tasks-route-name="`${item.id}-tasks`"
              :task-route-name="`${item.id}-task`"
              :active="activeModule === item.id"
              @toggle="toggleModule(item.id)"
            />
            <button
              v-show="collapsed"
              type="button"
              class="nav-item"
              :class="{ active: activeModule === item.id }"
              :title="item.label"
              @click="toggleModule(item.id)"
            >
              <el-icon class="nav-icon" :size="18"><component :is="iconMap[item.id]" /></el-icon>
            </button>
          </template>
        </section>
      </nav>

      <div class="sidebar-footer">
        <div v-show="!collapsed" class="sidebar-user">
          <div class="user-avatar">
            <el-icon :size="16"><UserFilled /></el-icon>
          </div>
          <div class="user-meta">
            <strong>{{ auth.user?.username || '用户' }}</strong>
            <button type="button" class="logout-link" @click="onLogout">退出登录</button>
          </div>
          <button type="button" class="icon-btn" title="退出" @click="onLogout">
            <el-icon :size="16"><Setting /></el-icon>
          </button>
        </div>
        <button
          type="button"
          class="collapse-rail-btn"
          :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="collapsed = !collapsed"
        >
          <el-icon :size="14">
            <DArrowRight v-if="collapsed" />
            <DArrowLeft v-else />
          </el-icon>
          <span v-show="!collapsed">收起侧边栏</span>
        </button>
      </div>
    </aside>

    <div class="app-shell">
      <header class="app-topbar">
        <div class="topbar-left">
          <div class="topbar-crumb">
            <span class="crumb-module">{{ currentNav.label }}</span>
            <span class="crumb-hint">{{ crumbHint() }}</span>
          </div>
        </div>
        <div class="topbar-right">
          <span class="user-pill">
            <span class="user-dot" />
            <span class="username">{{ auth.user?.username }}</span>
          </span>
          <el-button size="small" plain @click="onLogout">退出</el-button>
        </div>
      </header>

      <main class="app-content">
        <RouterView />
      </main>

      <footer class="app-footer">
        <span>© {{ PLATFORM_ORG }}</span>
        <span class="footer-tagline">{{ PLATFORM_TAGLINE }}</span>
      </footer>
    </div>
  </div>
</template>

<style scoped lang="scss">
.layout-root {
  --sidebar-width: 268px;
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  background:
    radial-gradient(ellipse 60% 40% at 12% 0%, rgba(0, 172, 161, 0.07), transparent 55%),
    radial-gradient(ellipse 50% 35% at 100% 0%, rgba(46, 90, 165, 0.06), transparent 50%),
    var(--bg);

  &.is-collapsed { --sidebar-width: 76px; }
}

.app-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(180deg, #ffffff 0%, #f7fbfb 42%, #f3f8fc 100%);
  color: var(--title);
  border-right: 1px solid var(--border);
  box-shadow: 4px 0 24px rgba(35, 35, 47, 0.04);
  z-index: 40;
  overflow: hidden;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.1rem 1rem 1rem;
  color: inherit;
  border-bottom: 1px solid var(--border);
  text-decoration: none;
}

.sidebar-logo {
  height: 36px;
  width: auto;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.22rem 0.32rem;
}

.sidebar-brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;

  strong {
    font-size: 0.9rem;
    font-weight: 700;
    line-height: 1.3;
    color: var(--title);
  }

  span {
    margin-top: 0.15rem;
    font-size: 0.62rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 0.85rem 0.7rem 0.6rem;
}

.nav-group + .nav-group {
  margin-top: 0.95rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.nav-group-label {
  margin: 0 0.45rem 0.45rem;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--muted);
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

.layout-root.is-collapsed .nav-item {
  justify-content: center;
  padding: 0.72rem 0.4rem;
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
.nav-chevron { flex-shrink: 0; opacity: 0.55; color: var(--muted); }

.fold-branch {
  border-radius: 12px;
  padding: 0.1rem;

  &.open,
  &.active {
    background: rgba(0, 172, 161, 0.06);
    border: 1px solid rgba(0, 172, 161, 0.2);
  }
}

.fold-submenu { padding: 0.15rem 0.4rem 0.55rem 0.55rem; }

.fold-link {
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

  &--new { color: var(--bio-green-dark); font-weight: 700; }
  &--all { margin-top: 0.25rem; color: var(--bio-blue); font-weight: 600; }
}

.fold-recent-head {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0.45rem 0.35rem 0.3rem;
  font-size: 0.68rem;
  color: var(--muted);
  font-weight: 600;
}

.fold-recent-list { max-height: 320px; overflow-y: auto; }
.fold-recent-empty {
  margin: 0.35rem 0.4rem;
  font-size: 0.72rem;
  color: var(--muted);
}

.fold-task {
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

.fold-task__dot {
  grid-row: 1 / span 2;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
  &.is-ok { background: var(--bio-green); }
  &.is-run { background: var(--warn); }
  &.is-fail { background: var(--err); }
}

.fold-task__kind {
  grid-column: 2;
  font-size: 0.58rem;
  font-weight: 700;
  padding: 0.02rem 0.28rem;
  border-radius: 3px;
  &.kind-single {
    background: var(--bio-blue-light);
    color: var(--bio-blue-dark);
  }
  &.kind-batch {
    background: var(--bio-green-light);
    color: var(--bio-green-dark);
  }
}

.fold-task__name {
  grid-column: 3;
  font-size: 0.74rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fold-task__status {
  grid-column: 4;
  font-size: 0.6rem;
  font-weight: 700;
  &.is-ok { color: var(--bio-green-dark); }
  &.is-run { color: #c67c00; }
  &.is-fail { color: var(--err); }
}

.fold-task__time {
  grid-column: 3 / span 2;
  font-size: 0.58rem;
  color: var(--muted);
}

.sidebar-footer {
  padding: 0.65rem 0.7rem 0.85rem;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.45rem 0.4rem;
  border-radius: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
  color: #fff;
  flex-shrink: 0;
}

.user-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  strong {
    font-size: 0.8rem;
    color: var(--title);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.logout-link {
  margin-top: 0.05rem;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  color: var(--muted);
  font-size: 0.66rem;
  cursor: pointer;
  &:hover { color: var(--bio-blue); }
}

.icon-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  &:hover {
    background: var(--bio-green-light);
    color: var(--bio-green-dark);
  }
}

.collapse-rail-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.45rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--body);
  font-size: 0.72rem;
  cursor: pointer;
  &:hover {
    background: var(--bio-green-light);
    border-color: rgba(0, 172, 161, 0.28);
    color: var(--bio-green-dark);
  }
}

.app-shell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  height: var(--app-topbar-height);
  padding: 0 1.25rem;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--border);
}

.topbar-left,
.topbar-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.topbar-crumb {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.crumb-module {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--title);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.crumb-hint {
  font-size: 0.72rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  background: var(--bio-blue-light);
  border: 1px solid rgba(46, 90, 165, 0.12);
  font-size: 0.8rem;
  color: var(--bio-blue-dark);
}

.user-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--bio-green);
}

.username { font-weight: 500; }

.app-content {
  flex: 1;
  padding: 1.15rem 1.35rem 1.6rem;
}

.app-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.45rem;
  padding: 0.7rem 1.35rem;
  font-size: 0.72rem;
  color: var(--muted);
  border-top: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.88);
}

@media (max-width: 960px) {
  .layout-root,
  .layout-root.is-collapsed { --sidebar-width: 76px; }

  .nav-label,
  .nav-badge,
  .nav-chevron,
  .sidebar-brand-text,
  .nav-group-label,
  .sidebar-user,
  .fold-submenu {
    display: none !important;
  }

  .crumb-hint { display: none; }
}
</style>
