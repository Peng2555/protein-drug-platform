<template>
  <div class="workspace">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.workspace {
  min-width: 0;
  min-height: calc(100vh - var(--app-topbar-height) - 72px);
}
</style>
