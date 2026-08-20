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
    <header class="fold-new__head">
      <h1>新建预测</h1>
      <p>单条 FASTA 或 VHH 批量提交，使用 Boltz2 / ESMFold2 预测复合物结构。</p>
    </header>
    <FoldSubmitForm />
  </div>
</template>

<style scoped lang="scss">
.fold-new {
  padding: 1.15rem 1.25rem 1.4rem;
}

.fold-new__head {
  margin-bottom: 1rem;

  h1 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--title);
  }

  p {
    margin: 0.35rem 0 0;
    font-size: 0.84rem;
    color: var(--muted);
  }
}
</style>
