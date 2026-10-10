<script setup lang="ts">
withDefaults(defineProps<{ count: number; tone?: 'green' | 'blue' }>(), { tone: 'blue' })
</script>

<template>
  <span v-if="count" class="count" :data-tone="tone">已识别 {{ count }} 条</span>
</template>

<style scoped>
.count {
  margin-left: 0.5rem;
  color: #1d4ed8;
}
.count[data-tone='green'] {
  color: #0f766e;
}
</style>
