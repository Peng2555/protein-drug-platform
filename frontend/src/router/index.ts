import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

function moduleChildren(
  base: string,
  labels: { module: string; new: string; tasks: string; task: string },
  views: {
    workspace: () => Promise<unknown>
    new: () => Promise<unknown>
    tasks: () => Promise<unknown>
    task: () => Promise<unknown>
  },
  extraChildren: RouteRecordRaw[] = [],
): RouteRecordRaw {
  return {
    path: base,
    component: views.workspace,
    meta: { title: labels.module },
    children: [
      { path: '', name: base, redirect: { name: `${base}-new` } },
      {
        path: 'new',
        name: `${base}-new`,
        component: views.new,
        meta: { title: labels.new },
      },
      {
        path: 'tasks',
        name: `${base}-tasks`,
        component: views.tasks,
        meta: { title: labels.tasks },
      },
      {
        path: 'task/:id',
        name: `${base}-task`,
        component: views.task,
        meta: { title: labels.task },
      },
      {
        path: 'jobs/:id',
        name: `${base}-job`,
        redirect: (to) => ({ name: `${base}-task`, params: { id: to.params.id } }),
      },
      ...extraChildren,
    ],
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/home' },
        {
          path: 'home',
          name: 'home',
          component: () => import('@/views/HomeView.vue'),
          meta: { title: '首页' },
        },
        {
          path: 'fold',
          component: () => import('@/views/fold/FoldWorkspaceView.vue'),
          meta: { title: '结构预测' },
          children: [
            { path: '', name: 'fold', redirect: { name: 'fold-new' } },
            {
              path: 'new',
              name: 'fold-new',
              component: () => import('@/views/fold/FoldNewView.vue'),
              meta: { title: '新建预测' },
            },
            {
              path: 'tasks',
              name: 'fold-tasks',
              component: () => import('@/views/fold/FoldTasksView.vue'),
              meta: { title: '全部任务' },
            },
            {
              path: 'task/:id',
              name: 'fold-task',
              component: () => import('@/views/fold/JobDetailView.vue'),
              meta: { title: '任务详情' },
            },
            {
              path: 'jobs/:id',
              name: 'fold-job',
              redirect: (to) => ({ name: 'fold-task', params: { id: to.params.id } }),
            },
            {
              path: 'batches/:id',
              name: 'fold-batch',
              component: () => import('@/views/fold/BatchDetailView.vue'),
              meta: { title: '批次详情' },
            },
          ],
        },
        moduleChildren(
          'design',
          {
            module: '序列设计',
            new: '新建设计',
            tasks: '全部任务',
            task: '设计详情',
          },
          {
            workspace: () => import('@/views/design/DesignWorkspaceView.vue'),
            new: () => import('@/views/design/DesignNewView.vue'),
            tasks: () => import('@/views/design/DesignTasksView.vue'),
            task: () => import('@/views/design/DesignJobDetailView.vue'),
          },
        ),
        moduleChildren(
          'rosetta',
          {
            module: '结构评价',
            new: '新建评价',
            tasks: '全部任务',
            task: '评价详情',
          },
          {
            workspace: () => import('@/views/rosetta/RosettaWorkspaceView.vue'),
            new: () => import('@/views/rosetta/RosettaNewView.vue'),
            tasks: () => import('@/views/rosetta/RosettaTasksView.vue'),
            task: () => import('@/views/rosetta/RosettaJobDetailView.vue'),
          },
        ),
        moduleChildren(
          'developability',
          {
            module: '序列改造',
            new: '新建改造',
            tasks: '全部任务',
            task: '改造详情',
          },
          {
            workspace: () => import('@/views/developability/DevelopabilityWorkspaceView.vue'),
            new: () => import('@/views/developability/DevelopabilityNewView.vue'),
            tasks: () => import('@/views/developability/DevelopabilityTasksView.vue'),
            task: () => import('@/views/developability/DevelopabilityJobDetailView.vue'),
          },
        ),
        moduleChildren(
          'maturation',
          {
            module: '亲和力成熟',
            new: '新建成熟',
            tasks: '全部任务',
            task: '成熟详情',
          },
          {
            workspace: () => import('@/views/maturation/MaturationWorkspaceView.vue'),
            new: () => import('@/views/maturation/MaturationNewView.vue'),
            tasks: () => import('@/views/maturation/MaturationTasksView.vue'),
            task: () => import('@/views/maturation/MaturationJobDetailView.vue'),
          },
        ),
        moduleChildren(
          'synthesis',
          {
            module: '合成候选',
            new: '新建筛选',
            tasks: '全部任务',
            task: '筛选结果',
          },
          {
            workspace: () => import('@/views/synthesis/SynthesisWorkspaceView.vue'),
            new: () => import('@/views/synthesis/SynthesisNewView.vue'),
            tasks: () => import('@/views/synthesis/SynthesisTasksView.vue'),
            task: () => import('@/views/synthesis/SynthesisJobDetailView.vue'),
          },
        ),
        {
          path: 'ras-docking/:pathMatch(.*)*',
          redirect: (to) =>
            to.params.pathMatch ? `/docking/${to.params.pathMatch}` : '/docking',
        },
        moduleChildren(
          'docking',
          {
            module: '分子对接',
            new: '新建对接',
            tasks: '全部任务',
            task: '对接详情',
          },
          {
            workspace: () => import('@/views/docking/DockingWorkspaceView.vue'),
            new: () => import('@/views/docking/DockingNewView.vue'),
            tasks: () => import('@/views/docking/DockingTasksView.vue'),
            task: () => import('@/views/docking/DockingJobDetailView.vue'),
          },
        ),
        moduleChildren(
          'md',
          {
            module: 'MD 验证',
            new: '新建 MD',
            tasks: '全部任务',
            task: 'MD 详情',
          },
          {
            workspace: () => import('@/views/md/MdWorkspaceView.vue'),
            new: () => import('@/views/md/MdNewView.vue'),
            tasks: () => import('@/views/md/MdTasksView.vue'),
            task: () => import('@/views/md/MdJobDetailView.vue'),
          },
        ),
        {
          path: 'legacy',
          name: 'legacy',
          component: () => import('@/views/LegacyFrameView.vue'),
          meta: { title: '经典界面' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (auth.isLoggedIn && to.name === 'login') return { name: 'home' }
    return true
  }
  if (!auth.isLoggedIn) {
    const ok = await auth.bootstrap()
    if (!ok) return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  const page = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = page
    ? `${page} · 蛋白质-药物计算平台`
    : '蛋白质-药物计算平台 · 百奥赛图'
})

export default router
