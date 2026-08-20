<template>
  <div class="page-card page-card--accent empty-panel">
    <h2>序列改造（可开发性）</h2>
    <p>
      用本地 <strong>ESM-2 3B</strong> 和（可选）<strong>Venus-MAXWELL</strong> 并列打分。
      位点能不能动，仍由 ESM-2 ΔLL 决定；MAXWELL 给出结构相对 ΔΔG，数值越低越稳。
    </p>
    <ol>
      <li>绿色 = 可以突变；点开同时看 ΔLL 和 ΔΔG</li>
      <li>灰色 = 保护规则冻住；蓝色 = 野生型已经很稳，不建议动</li>
      <li>没有结构时 MAXWELL 会跳过，ESM-2 照常出结果</li>
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
