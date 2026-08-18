<template>
  <div class="empty-panel page-card">
    <h2>合成候选筛选</h2>
    <p>上传 SHM 测序大表 + IgGM 突变表，交叉比对后输出<strong>送合成清单</strong>（A/B 档）。</p>
    <ul class="file-hint">
      <li><strong>SHM 大表</strong>：体细胞高频突变表（含 <code>kabat_FR1…FR4</code>、<code>kabat_CDR3</code> 等 Kabat 区段列）</li>
      <li><strong>IgGM 表</strong>：<code>cdr3_all_1to3.csv</code></li>
      <li><strong>origin.fasta</strong>（可选）：用于在 SHM 表中定位母本参考行</li>
    </ul>
    <p class="hint">
      CDR3 边界由 SHM 表 Kabat 注释自动计算，无需 mask.fasta。
      匹配规则：IgGM <code>cdr3_seq</code> 与 SHM <code>kabat_CDR3</code> 精确匹配；
      额外 SHM 按 Kabat 区段相对母本参考序列识别。
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

  p,
  .file-hint {
    margin: 0 0 0.5rem;
    color: var(--el-text-color-secondary);
    line-height: 1.6;
  }

  .file-hint {
    padding-left: 1.25rem;
  }

  .hint {
    font-size: 0.85rem;
    margin-top: 1rem;
  }
}
</style>
