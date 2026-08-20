<script setup lang="ts">
/**
 * 相互作用表格（工作台右侧复用入口）。
 * 实际渲染与筛选逻辑仍在 InterfacePanel 内，避免双份状态。
 */
import InterfacePanel from '@/components/structure/InterfacePanel.vue'
import type { InterfaceInteraction, JobInterfaceData } from '@/types/structure'

defineProps<{
  jobId: string
  chainCount?: number
  cifText?: string | null
}>()

const emit = defineEmits<{
  loaded: [data: JobInterfaceData]
  'focus-interaction': [ix: InterfaceInteraction]
}>()
</script>

<template>
  <InterfacePanel
    hide-viewer
    table-only
    :job-id="jobId"
    :chain-count="chainCount ?? 2"
    :cif-text="cifText"
    @loaded="emit('loaded', $event)"
    @focus-interaction="emit('focus-interaction', $event)"
  />
</template>
