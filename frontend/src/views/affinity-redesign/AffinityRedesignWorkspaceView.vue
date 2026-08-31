<script setup lang="ts">
/** 亲和力改造工作区 */
</script>

<template>
  <div class="affinity-redesign-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.affinity-redesign-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
