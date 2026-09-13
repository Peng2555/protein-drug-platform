<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteCicProfileJob } from '@/api/cicProfile'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { cicProfileJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  cicProfileJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || 'CIC',
  })),
)

async function refresh() {
  try {
    await store.refreshCicProfile()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteCicProfileJob(id)
    if (route.name === 'cic-profile-task' && route.params.id === id) {
      router.push({ name: 'cic-profile-tasks' })
    }
    await store.refreshCicProfile()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="Boltz2 折抗体 → 实验 pH 有效电荷 × 表面暴露 → 正电 / 负电 / 疏水斑"
    kind-label="CIC"
    task-route-name="cic-profile-task"
    new-route-name="cic-profile-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
