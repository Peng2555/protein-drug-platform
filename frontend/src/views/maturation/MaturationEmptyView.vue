<template>
  <div class="empty-panel page-card">
    <h2>亲和力成熟</h2>
    <p>在左侧选择复合物结构来源与 IgGM 参数；使用已有结构或折叠任务时可不填 FASTA（自动从结构/任务读取序列）。</p>
    <p class="hint">支持上传 PDB/CIF、Boltz2/ESMFold2 预测结构，或选用已有折叠任务作为复合物输入。</p>
    <p class="hint">
      送合成候选筛选请使用顶部导航
      <RouterLink to="/synthesis">「合成候选」</RouterLink>
      ，可独立上传测序表与 IgGM 突变表，无需在本模块提交任务。
    </p>
  </div>
</template>

<style scoped lang="scss">
.empty-panel {
  padding: 2rem;
  min-height: 100%;

  h2 {
    margin: 0 0 0.75rem;
  }

  p {
    margin: 0 0 0.5rem;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
  }

  .hint {
    font-size: 0.85rem;
  }
}
</style>
