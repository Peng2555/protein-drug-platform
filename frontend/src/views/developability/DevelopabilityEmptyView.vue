<template>
  <div class="page-card page-card--accent empty-panel">
    <h2>序列改造（可开发性）</h2>
    <p>
      用本地 ESM-2 3B 标出<strong>可以突变的位点</strong>以及<strong>能换成哪些氨基酸</strong>。
      亲水性、Tm 不在这一步决定。
    </p>
    <ol>
      <li>绿色 = 可以突变；点开看能换成哪些氨基酸</li>
      <li>灰色 = 保护规则冻住；蓝色 = 野生型已经很稳，不建议动</li>
      <li>下面的位点表汇总每个可突变位置允许的氨基酸</li>
    </ol>
    <p class="hint">默认冻住 Cys 和 CDR3。ΔLL ≥ 0 的非 Cys 替换都会列出。</p>
  </div>
</template>

<style scoped lang="scss">
.empty-panel {
  padding: 2rem;
  min-height: 420px;
  h2 { margin: 0 0 0.75rem; }
  p, ol { color: var(--text-muted); line-height: 1.6; }
  .hint { font-size: 0.85rem; }
}
</style>
