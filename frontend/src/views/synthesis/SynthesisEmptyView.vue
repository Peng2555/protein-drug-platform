<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="合成候选筛选"
    subtitle="上传 SHM 测序大表与 IgGM 突变表，交叉比对后输出送合成清单（A/B 档）。"
    :tips="[
      'SHM 大表需含 Kabat FR/CDR 区段列',
      'IgGM 表使用 cdr3_all_1to3.csv',
      '可选 origin.fasta，用于在 SHM 表中定位母本参考行',
    ]"
  />
</template>
