<script setup lang="ts">
/** 抗体额外二硫键工作区 */
</script>

<template>
  <div class="tm-disulfide-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.tm-disulfide-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
