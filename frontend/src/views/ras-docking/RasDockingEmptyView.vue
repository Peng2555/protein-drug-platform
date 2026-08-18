<template>
  <div class="page-card page-card--accent empty-panel">
    <el-empty description="选择左侧阶段并提交一个 RAS 三元复合物对接任务" />
    <p>RMC-6236 支持参考结构准备、redock、文献化合物对接、SDF 筛选和接触分析；RMC-6291 支持结构准备与 constrained docking。</p>
  </div>
</template>

<style scoped>
.empty-panel { min-height: 420px; padding: 3rem; }
.empty-panel p { max-width: 620px; margin: 0 auto; color: var(--text-muted); text-align: center; }
</style>
