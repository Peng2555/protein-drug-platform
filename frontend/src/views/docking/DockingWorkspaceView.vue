<template>
  <div class="docking-workspace-stage">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.docking-workspace-stage {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
