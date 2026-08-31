<script setup lang="ts">
/** 多肽遮蔽设计工作区 */
</script>

<template>
  <div class="masking-peptide-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.masking-peptide-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
