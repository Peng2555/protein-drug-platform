<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteMaturationJob } from '@/api/maturation'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { MATURATION_STAGE_LABELS } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()
const foldStore = useFoldTasksStore()

const jobs = computed(() =>
  moduleJobs.maturationJobs.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: `IgGM${j.stage ? ` · ${MATURATION_STAGE_LABELS[j.stage] || j.stage}` : ''}`,
  })),
)

async function onRefresh() {
  await Promise.all([moduleJobs.refreshMaturation(), foldStore.refreshMaturationTasks()])
}

async function onDelete(id: string) {
  try {
    await deleteMaturationJob(id)
    const onTask =
      (route.name === 'maturation-task' || route.name === 'maturation-job') &&
      route.params.id === id
    if (onTask) router.push({ name: 'maturation-tasks' })
    await Promise.all([moduleJobs.refreshMaturation(), foldStore.refreshMaturationTasks()])
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部成熟任务"
    subtitle="IgGM 亲和力成熟任务列表"
    kind-label="成熟"
    task-route-name="maturation-task"
    new-route-name="maturation-new"
    :jobs="jobs"
    :loading="moduleJobs.loading"
    @refresh="onRefresh"
    @delete="onDelete"
  />
</template>
