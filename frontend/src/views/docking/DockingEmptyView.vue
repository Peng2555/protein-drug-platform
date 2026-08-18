<template>
  <div class="page-card page-card--accent empty-panel">
    <el-empty description="填写小分子 SMILES，开始对接" />
    <p>
      流程：SMILES → ETKDGv3 构象采样作为起点 → Meeko 准备（大环可动）→ 全局 AutoDock Vina。
      不使用上传的配体三维坐标。适用于任意靶点。
    </p>
  </div>
</template>

<style scoped>
.empty-panel { min-height: 420px; padding: 3rem; }
.empty-panel p { max-width: 620px; margin: 0 auto; text-align: center; color: var(--text-muted); }
</style>
