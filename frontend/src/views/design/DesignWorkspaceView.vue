<script setup lang="ts">
/** 序列设计工作区：任务列表已并入左侧导航 */
</script>

<template>
  <div class="design-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.design-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
