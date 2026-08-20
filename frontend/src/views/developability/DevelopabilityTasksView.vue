<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteDevelopabilityJob } from '@/api/developability'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { developabilityJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  developabilityJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: `${j.total_length ?? '—'} aa`,
  })),
)

async function refresh() {
  try {
    await store.refreshDevelopability()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteDevelopabilityJob(id)
    if (route.name === 'developability-task' && route.params.id === id) {
      router.push({ name: 'developability-tasks' })
    }
    await store.refreshDevelopability()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="序列改造 ESM-2 与 MAXWELL 打分任务"
    kind-label="改造"
    task-route-name="developability-task"
    new-route-name="developability-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
