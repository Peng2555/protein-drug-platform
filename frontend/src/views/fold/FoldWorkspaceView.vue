<script setup lang="ts">
import FoldSidebar from '@/components/fold/FoldSidebar.vue'
</script>

<template>
  <div class="fold-workspace">
    <FoldSidebar />
    <div class="fold-main">
      <RouterView />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
</style>
