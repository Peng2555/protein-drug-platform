<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="分子对接"
    subtitle="参考 CB-Dock：自动搜索口袋并盲对接，也可指定已知口袋。适用于小分子药物筛选。"
    :tips="[
      '自动盲对接：口袋检测 → 多口袋 Vina → 亲和力排序',
      '配体可用 SMILES 或上传 mol2/sdf；不使用上传配体三维坐标作为起点',
      '也支持参考配体定口袋或手动搜索盒',
    ]"
  />
</template>
