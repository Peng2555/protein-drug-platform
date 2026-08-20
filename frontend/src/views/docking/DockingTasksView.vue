<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteDockingJob } from '@/api/docking'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()

const jobs = computed(() =>
  moduleJobs.dockingJobs.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: `${j.params_json?.engine ?? ''}${j.stage ? ` · ${j.stage}` : ''}`.trim(),
  })),
)

async function onRefresh() {
  await moduleJobs.refreshDocking()
}

async function onDelete(id: string) {
  try {
    await deleteDockingJob(id)
    const onTask =
      (route.name === 'docking-task' || route.name === 'docking-job') && route.params.id === id
    if (onTask) router.push({ name: 'docking-tasks' })
    await moduleJobs.refreshDocking()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部对接任务"
    subtitle="分子对接任务列表（口袋检测 / 盲对接 / 指定口袋）"
    kind-label="对接"
    task-route-name="docking-task"
    new-route-name="docking-new"
    :jobs="jobs"
    :loading="moduleJobs.loading"
    @refresh="onRefresh"
    @delete="onDelete"
  />
</template>
