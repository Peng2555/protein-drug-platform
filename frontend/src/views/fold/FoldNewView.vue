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
  <div class="fold-new">
    <FoldSubmitForm />
  </div>
</template>

<style scoped lang="scss">
.fold-new {
  padding: 0.25rem 0 1.5rem;
}
</style>
