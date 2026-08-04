<template>
  <div class="detail-empty page-card page-card--accent">
    <div class="empty-icon" aria-hidden="true">◎</div>
    <h2>MD 验证</h2>
    <p>在左侧选择已完成折叠任务，或上传结构文件，提交 GROMACS 模拟。</p>
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
  color: var(--bio-blue-dark);
  background: linear-gradient(135deg, var(--bio-blue-light), var(--bio-green-light));
  border-radius: 16px;
  border: 1px solid rgba(46, 90, 165, 0.15);
}
</style>
