<script setup lang="ts">
import ModuleHome from '@/components/layout/ModuleHome.vue'
</script>

<template>
  <ModuleHome
    title="序列改造"
    subtitle="用本地 ESM-2 3B 与（可选）Venus-MAXWELL 并列打分：ESM-2 ΔLL 决定位点能不能动，MAXWELL 给出结构相对 ΔΔG。"
    :tips="[
      '绿色 = 可以突变；点开同时看 ΔLL 和 ΔΔG',
      '灰色 = 保护规则冻住；蓝色 = 野生型已经很稳',
      '没有结构时 MAXWELL 会跳过，ESM-2 照常出结果',
    ]"
  />
</template>
