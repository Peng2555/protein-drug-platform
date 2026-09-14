<script setup lang="ts">
/** VHH 可开发性画像工作区 */
</script>

<template>
  <div class="tnp-profile-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.tnp-profile-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
