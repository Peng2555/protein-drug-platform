<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteHydroRedesignJob } from '@/api/hydroRedesign'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { hydroRedesignJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  hydroRedesignJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || '疏水改造',
  })),
)

async function refresh() {
  try {
    await store.refreshHydroRedesign()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteHydroRedesignJob(id)
    if (route.name === 'hydro-redesign-task' && route.params.id === id) {
      router.push({ name: 'hydro-redesign-tasks' })
    }
    await store.refreshHydroRedesign()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="Boltz2 折抗体 → 表面疏水斑 → 亲水突变枚举（不重折）"
    kind-label="疏水"
    task-route-name="hydro-redesign-task"
    new-route-name="hydro-redesign-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
