<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="亲和力成熟"
    subtitle="用 IgGM 在指定 CDR 上采样变体。可上传 PDB/CIF、预测结构，或直接选用已有折叠任务作为复合物输入。"
    :tips="[
      '使用已有结构或折叠任务时可不填 FASTA',
      '支持 Boltz2 / ESMFold2 预测结构作为输入',
      '送合成候选请到「合成候选」模块，无需在此提交筛选任务',
    ]"
  />
</template>
