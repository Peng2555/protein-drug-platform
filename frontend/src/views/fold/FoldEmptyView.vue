<template>
  <div class="detail-empty page-card page-card--accent">
    <div class="empty-icon" aria-hidden="true">⬡</div>
    <h2>选择任务或提交新预测</h2>
    <p>在左侧提交单条 / VHH 批量任务，或从任务列表中选择查看详情。</p>
    <ul class="empty-tips">
      <li>单条预测：粘贴 FASTA，支持 Boltz2 / ESMFold2</li>
      <li>VHH 批量：导入 CSV / Excel / FASTA 重链列表</li>
      <li>完成后可查看 3D 结构、序列编号与 PLIP 结合界面</li>
    </ul>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';

.empty-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 1rem;
  display: grid;
  place-items: center;
  font-size: 1.6rem;
  color: var(--bio-green-dark);
  background: linear-gradient(135deg, var(--bio-green-light), var(--bio-blue-light));
  border-radius: 16px;
  border: 1px solid rgba(0, 172, 161, 0.15);
}

.empty-tips {
  list-style: none;
  margin: 1.25rem auto 0;
  padding: 0;
  max-width: 420px;
  text-align: left;

  li {
    position: relative;
    padding: 0.35rem 0 0.35rem 1.1rem;
    font-size: 0.82rem;
    color: var(--body);

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0.72rem;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--bio-green);
    }
  }
}
</style>
