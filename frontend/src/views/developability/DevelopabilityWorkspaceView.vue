<script setup lang="ts">
/** 序列改造工作区：任务列表已并入左侧导航 */
</script>

<template>
  <div class="developability-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.developability-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
