<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModuleTasksPage from '@/components/layout/ModuleTasksPage.vue'
import { deleteMaskingPeptideJob } from '@/api/maskingPeptide'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useModuleJobsStore()
const { maskingPeptideJobs, loading } = storeToRefs(store)

const jobs = computed(() =>
  maskingPeptideJobs.value.map((j) => ({
    id: j.id,
    name: j.name,
    status: j.status,
    created_at: j.created_at,
    meta: j.stage || '多肽遮蔽',
  })),
)

async function refresh() {
  try {
    await store.refreshMaskingPeptide()
  } catch {
    /* ignore */
  }
}

async function onDelete(id: string) {
  try {
    await deleteMaskingPeptideJob(id)
    if (route.name === 'masking-peptide-task' && route.params.id === id) {
      router.push({ name: 'masking-peptide-tasks' })
    }
    await store.refreshMaskingPeptide()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}
</script>

<template>
  <ModuleTasksPage
    title="全部任务"
    subtitle="RFdiffusion 骨架生成 → MPNN + 环化 FastRelax → 序列导出"
    kind-label="多肽"
    task-route-name="masking-peptide-task"
    new-route-name="masking-peptide-new"
    :jobs="jobs"
    :loading="loading"
    @refresh="refresh"
    @delete="onDelete"
  />
</template>
