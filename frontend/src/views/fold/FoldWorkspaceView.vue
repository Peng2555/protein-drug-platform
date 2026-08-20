<script setup lang="ts">
/** 结构预测工作区：任务列表已并入左侧导航 */
</script>

<template>
  <div class="fold-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.fold-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
