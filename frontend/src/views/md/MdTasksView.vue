<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteMdJob } from '@/api/md'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { MD_STAGE_LABELS } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()

const jobs = computed(() =>
  moduleJobs.mdJobs.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: `GROMACS MD${j.stage ? ` · ${MD_STAGE_LABELS[j.stage] || j.stage}` : ''}`,
  })),
)

async function onRefresh() {
  await moduleJobs.refreshMd()
}

async function onDelete(id: string) {
  try {
    await deleteMdJob(id)
    const onTask =
      (route.name === 'md-task' || route.name === 'md-job') && route.params.id === id
    if (onTask) router.push({ name: 'md-tasks' })
    await moduleJobs.refreshMd()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部 MD 任务"
    subtitle="GROMACS 显式溶剂 MD 验证任务列表"
    kind-label="MD"
    task-route-name="md-task"
    new-route-name="md-new"
    :jobs="jobs"
    :loading="moduleJobs.loading"
    @refresh="onRefresh"
    @delete="onDelete"
  />
</template>
