<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteSynthesisJob } from '@/api/synthesis'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const route = useRoute()
const router = useRouter()
const moduleJobs = useModuleJobsStore()

const jobs = computed(() =>
  moduleJobs.synthesisJobs.map((j) => {
    const r = j.results_json as Record<string, number> | null
    let meta = ''
    if (r) {
      const parts: string[] = []
      if (r.matched_count != null) parts.push(`匹配 ${r.matched_count}`)
      if (r.order_count != null) parts.push(`送合成 ${r.order_count}`)
      meta = parts.join(' · ')
    }
    return {
      id: j.id,
      name: j.name,
      status: j.status,
      created_at: j.created_at,
      meta,
    }
  }),
)

async function onRefresh() {
  await moduleJobs.refreshSynthesis()
}

async function onDelete(id: string) {
  try {
    await deleteSynthesisJob(id)
    const onTask =
      (route.name === 'synthesis-task' || route.name === 'synthesis-job') &&
      route.params.id === id
    if (onTask) router.push({ name: 'synthesis-tasks' })
    await moduleJobs.refreshSynthesis()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部筛选记录"
    subtitle="SHM 与 IgGM 交叉比对后的合成候选任务列表"
    kind-label="合成"
    task-route-name="synthesis-task"
    new-route-name="synthesis-new"
    :jobs="jobs"
    :loading="moduleJobs.loading"
    @refresh="onRefresh"
    @delete="onDelete"
  />
</template>
