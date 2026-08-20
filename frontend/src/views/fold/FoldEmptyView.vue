<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="结构预测"
    subtitle="粘贴 FASTA 或导入 VHH 重链列表，用 Boltz2 / ESMFold2 预测复合物结构，完成后可查看 3D、序列编号与结合界面。"
    :tips="[
      '单条预测：粘贴 FASTA，支持 Boltz2 / ESMFold2',
      'VHH 批量：导入 CSV / Excel / FASTA 重链列表',
      '完成后可查看 Mol* 结构、序列编号与 PLIP 界面',
    ]"
  />
</template>
