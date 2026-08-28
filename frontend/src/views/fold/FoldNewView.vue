<script setup lang="ts">
import { onMounted } from 'vue'
import FoldSubmitForm from '@/components/fold/FoldSubmitForm.vue'
import { useFoldTasksStore } from '@/stores/foldTasks'

const store = useFoldTasksStore()

onMounted(() => {
  void store.refreshFoldTasks()
  store.startPolling()
})
</script>

<template>
  <div class="fold-new page-card">
    <header class="workbench-form-head">
      <h1>新建预测</h1>
      <p>单条 FASTA 或 VHH 批量提交，使用 Boltz2 / ESMFold2 预测复合物结构。</p>
    </header>
    <FoldSubmitForm />
  </div>
</template>

<style scoped lang="scss">
.fold-new {
  padding: 1.35rem 1.5rem 1.5rem;
}
</style>
