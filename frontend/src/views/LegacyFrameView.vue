<script setup lang="ts">
/** 迁移过渡期：iframe 加载旧版静态页（需后端同时保留 web/ 静态资源） */
</script>

<template>
  <div class="legacy-frame page-card">
    <el-alert
      title="经典界面（Vanilla JS）"
      type="warning"
      :closable="false"
      show-icon
      class="banner"
    >
      完整 3D、Kabat 序列、PLIP 结合界面等功能目前仍在此经典页面中。Vue 版将逐步替换。
    </el-alert>
    <iframe class="legacy-iframe" src="/legacy-app/index.html" title="BoltzFold Legacy UI" />
  </div>
</template>

<style scoped lang="scss">
.legacy-frame {
  overflow: hidden;
  padding: 0.75rem;
}

.banner {
  margin-bottom: 0.75rem;
}

.legacy-iframe {
  width: 100%;
  height: calc(100vh - 220px);
  min-height: 640px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
}
</style>
