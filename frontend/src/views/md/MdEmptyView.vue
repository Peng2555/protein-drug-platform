<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="MD 验证"
    subtitle="从已完成折叠任务或上传的 CIF/PDB 发起 GROMACS 显式溶剂模拟，用于评估结构稳定性。"
    :tips="[
      '可选用已完成的结构预测任务作为起点',
      '也可直接上传 CIF / PDB',
      '任务在 GPU 队列中运行，完成后查看轨迹与阶段摘要',
    ]"
  />
</template>
