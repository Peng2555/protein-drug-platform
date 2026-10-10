<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteTmDisulfideJob } from '@/api/tmDisulfide'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { tmDisulfideJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  tmDisulfideJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || '二硫键',
  })),
)

async function refresh() {
  try {
    await store.refreshTmDisulfide()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteTmDisulfideJob(id)
    if (route.name === 'tm-disulfide-task' && route.params.id === id) {
      router.push({ name: 'tm-disulfide-tasks' })
    }
    await store.refreshTmDisulfide()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="已有 Boltz2 作业 → 质控 / 几何 / 成键 / 折叠态能量"
    kind-label="二硫键"
    task-route-name="tm-disulfide-task"
    new-route-name="tm-disulfide-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
