<script setup lang="ts">
/** 结构评价工作区 */
</script>

<template>
  <div class="rosetta-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.rosetta-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
