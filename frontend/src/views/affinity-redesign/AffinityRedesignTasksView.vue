<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteAffinityRedesignJob } from '@/api/affinityRedesign'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { affinityRedesignJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  affinityRedesignJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || '亲和力改造',
  })),
)

async function refresh() {
  try {
    await store.refreshAffinityRedesign()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteAffinityRedesignJob(id)
    if (route.name === 'affinity-redesign-task' && route.params.id === id) {
      router.push({ name: 'affinity-redesign-tasks' })
    }
    await store.refreshAffinityRedesign()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="亲和力改造端到端流水线（round1 → Boltz2 → Rosetta）"
    kind-label="改造"
    task-route-name="affinity-redesign-task"
    new-route-name="affinity-redesign-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
