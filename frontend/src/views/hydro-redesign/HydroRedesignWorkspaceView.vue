<script setup lang="ts">
/** 抗体疏水性改造工作区 */
</script>

<template>
  <div class="hydro-redesign-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.hydro-redesign-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
