<script setup lang="ts">
/** 抗体 CIC 表面斑工作区 */
</script>

<template>
  <div class="cic-profile-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.cic-profile-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
