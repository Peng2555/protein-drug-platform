<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteDesignJob } from '@/api/design'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { designJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  designJobs.value.map((j) => {
    const chains = j.params_json && typeof j.params_json.designed_chains === 'string'
      ? j.params_json.designed_chains
      : ''
    return {
      id: j.id,
      name: j.name,
      status: j.status,
      created_at: j.created_at,
      meta: chains ? `链 ${chains}` : 'ProteinMPNN',
    }
  }),
)

async function refresh() {
  try {
    await store.refreshDesign()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteDesignJob(id)
    if (route.name === 'design-task' && route.params.id === id) {
      router.push({ name: 'design-tasks' })
    }
    await store.refreshDesign()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="ProteinMPNN 序列设计任务"
    kind-label="设计"
    task-route-name="design-task"
    new-route-name="design-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
