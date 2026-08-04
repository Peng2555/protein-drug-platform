<template>
  <div class="empty-panel page-card">
    <h2>亲和力成熟</h2>
    <p>在左侧填写 Parent FASTA、选择复合物结构来源与 IgGM 参数，提交 IgGM 亲和力成熟任务。</p>
    <p class="hint">支持上传 PDB/CIF、Boltz2/ESMFold2 预测结构，或选用已有折叠任务作为复合物输入。</p>
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
