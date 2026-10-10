<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteTnpProfileBatch, deleteTnpProfileJob } from '@/api/tnpProfile'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { tnpProfileJobs, tnpProfileBatches, loading } = storeToRefs(store)

const jobs = computed(() => {
  const singles = tnpProfileJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || '画像',
    kindLabel: '单条',
    routeName: 'tnp-profile-task',
  }))
  const batches = tnpProfileBatches.value.map((b) => ({
    id: b.id,
    name: b.name,
    status: b.status,
    created_at: b.created_at,
    meta: `${b.done_count}/${b.heavy_chain_count} 完成`,
    kindLabel: '批次',
    routeName: 'tnp-profile-batch',
  }))
  return [...singles, ...batches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
})

async function refresh() {
  try {
    await store.refreshTnpProfile()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  const batch = tnpProfileBatches.value.find((b) => b.id === id)
  try {
    if (batch) {
      await deleteTnpProfileBatch(id)
      if (route.name === 'tnp-profile-batch' && route.params.id === id) {
        router.push({ name: 'tnp-profile-tasks' })
      }
    } else {
      await deleteTnpProfileJob(id)
      if (route.name === 'tnp-profile-task' && route.params.id === id) {
        router.push({ name: 'tnp-profile-tasks' })
      }
    }
    await store.refreshTnpProfile()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="Boltz2 折 VHH → Kabat 编号 → 六项可开发性指标"
    kind-label="画像"
    task-route-name="tnp-profile-task"
    new-route-name="tnp-profile-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
