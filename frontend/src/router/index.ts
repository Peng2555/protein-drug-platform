import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/fold' },
        {
          path: 'fold',
          component: () => import('@/views/fold/FoldWorkspaceView.vue'),
          meta: { title: '结构预测' },
          children: [
            {
              path: '',
              name: 'fold',
              component: () => import('@/views/fold/FoldEmptyView.vue'),
            },
            {
              path: 'jobs/:id',
              name: 'fold-job',
              component: () => import('@/views/fold/JobDetailView.vue'),
              meta: { title: '任务详情' },
            },
            {
              path: 'batches/:id',
              name: 'fold-batch',
              component: () => import('@/views/fold/BatchDetailView.vue'),
              meta: { title: '批次详情' },
            },
          ],
        },
        {
          path: 'md',
          component: () => import('@/views/md/MdWorkspaceView.vue'),
          meta: { title: 'MD 验证' },
          children: [
            {
              path: '',
              name: 'md',
              component: () => import('@/views/md/MdEmptyView.vue'),
            },
            {
              path: 'jobs/:id',
              name: 'md-job',
              component: () => import('@/views/md/MdJobDetailView.vue'),
              meta: { title: 'MD 详情' },
            },
          ],
        },
        {
          path: 'maturation',
          component: () => import('@/views/maturation/MaturationWorkspaceView.vue'),
          meta: { title: '亲和力成熟' },
          children: [
            {
              path: '',
              name: 'maturation',
              component: () => import('@/views/maturation/MaturationEmptyView.vue'),
            },
            {
              path: 'jobs/:id',
              name: 'maturation-job',
              component: () => import('@/views/maturation/MaturationJobDetailView.vue'),
              meta: { title: '成熟详情' },
            },
          ],
        },
        {
          path: 'legacy',
          name: 'legacy',
          component: () => import('@/views/LegacyFrameView.vue'),
          meta: { title: '经典界面' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/fold' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (auth.isLoggedIn && to.name === 'login') return { name: 'fold' }
    return true
  }
  if (!auth.isLoggedIn) {
    const ok = await auth.bootstrap()
    if (!ok) return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
