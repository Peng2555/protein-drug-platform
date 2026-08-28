<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteRosettaEvalJob } from '@/api/rosetta'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { rosettaJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  rosettaJobs.value.map((j) => {
    const n = Array.isArray(j.params_json?.variants) ? j.params_json.variants.length : 0
    return {
      id: j.id,
      name: j.name,
      status: j.status,
      created_at: j.created_at,
      meta: n ? `${n} 个结构` : 'Rosetta',
    }
  }),
)

async function refresh() {
  try {
    await store.refreshRosetta()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteRosettaEvalJob(id)
    if (route.name === 'rosetta-task' && route.params.id === id) {
      router.push({ name: 'rosetta-tasks' })
    }
    await store.refreshRosetta()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="Rosetta 抗体–抗原结构评价"
    kind-label="评价"
    task-route-name="rosetta-task"
    new-route-name="rosetta-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
