<script setup lang="ts">
import { Document, UploadFilled } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    modelValue: File | null
    title: string
    accent?: 'green' | 'blue'
  }>(),
  { accent: 'blue' },
)

const emit = defineEmits<{ 'update:modelValue': [value: File | null] }>()

function onChange(arg: { raw?: File }) {
  emit('update:modelValue', arg.raw || null)
}
</script>

<template>
  <div v-if="modelValue" class="upload-done">
    <el-icon><Document /></el-icon>
    <span>{{ modelValue.name }}</span>
    <button type="button" class="link-btn" @click="emit('update:modelValue', null)">移除</button>
  </div>
  <el-upload
    v-else
    drag
    class="upload-zone"
    :auto-upload="false"
    :limit="1"
    :show-file-list="false"
    accept=".pdb,.cif,.mmcif"
    @change="onChange"
  >
    <el-icon class="upload-zone__icon" :data-accent="accent"><UploadFilled /></el-icon>
    <p class="upload-zone__title">{{ title }}</p>
  </el-upload>
</template>

<style scoped lang="scss">
.upload-done {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  font-size: 0.85rem;
}
.upload-zone {
  width: 100%;
  :deep(.el-upload-dragger) {
    padding: 1.5rem;
    border-radius: 12px;
  }
}
.upload-zone__icon {
  font-size: 2rem;
  color: #2563eb;
}
.upload-zone__icon[data-accent='green'] {
  color: var(--bio-green, #00aca1);
}
.upload-zone__title {
  margin: 0.5rem 0 0;
  font-size: 0.88rem;
}
.link-btn {
  margin-left: 0.35rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--bio-blue, #2563eb);
  font-size: 0.8rem;
  cursor: pointer;
}
</style>
