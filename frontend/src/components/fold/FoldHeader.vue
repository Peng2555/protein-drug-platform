<script setup lang="ts">
defineProps<{
  title: string
  crumbParent?: string
  statusLabel?: string
  statusType?: 'success' | 'warning' | 'danger' | 'info'
  finishedText?: string
  tags?: string[]
  showMd?: boolean
  showDesign?: boolean
  showExport?: boolean
}>()

const emit = defineEmits<{
  back: []
  startMd: []
  startDesign: []
  export: []
  delete: []
}>()
</script>

<template>
  <header class="fold-header">
    <div class="fold-header__crumb">
      <button type="button" class="crumb-link" @click="emit('back')">
        {{ crumbParent || '结构预测' }}
      </button>
      <span class="crumb-sep">/</span>
      <span class="crumb-current">{{ title }}</span>
    </div>

    <div class="fold-header__row">
      <div class="fold-header__title-block">
        <h1>{{ title }}</h1>
        <div v-if="tags?.length" class="fold-header__tags">
          <span v-for="tag in tags" :key="tag" class="meta-tag">{{ tag }}</span>
        </div>
      </div>

      <div class="fold-header__actions">
        <div v-if="statusLabel" class="status-pill">
          <el-tag :type="statusType || 'info'" size="small" effect="light">
            {{ statusLabel }}
          </el-tag>
          <span v-if="finishedText" class="status-time">{{ finishedText }}</span>
        </div>
        <el-button v-if="showDesign" @click="emit('startDesign')">启动序列设计</el-button>
        <el-button v-if="showMd" type="primary" @click="emit('startMd')">启动 MD</el-button>
        <el-button v-if="showExport" @click="emit('export')">导出结构</el-button>
        <el-button type="danger" plain @click="emit('delete')">删除</el-button>
      </div>
    </div>
  </header>
</template>

<style scoped lang="scss">
.fold-header {
  padding: 0.1rem 0.1rem 0.2rem;
}

.fold-header__crumb {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.4rem;
  font-size: 0.78rem;
  color: var(--muted);
}

.crumb-link {
  border: none;
  background: transparent;
  color: var(--bio-blue);
  cursor: pointer;
  padding: 0;
  font-size: inherit;

  &:hover {
    color: var(--bio-blue-dark);
  }
}

.crumb-sep { opacity: 0.5; }
.crumb-current {
  color: var(--body);
  font-weight: 600;
}

.fold-header__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.fold-header__title-block {
  min-width: 0;
  flex: 1;

  h1 {
    margin: 0;
    font-size: 1.28rem;
    font-weight: 700;
    color: var(--title);
    letter-spacing: -0.02em;
    line-height: 1.25;
  }
}

.fold-header__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.5rem;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(0, 172, 161, 0.22);
  background: var(--bio-green-light);
  color: var(--bio-green-dark);
  font-size: 0.72rem;
  font-weight: 600;
}

.fold-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin-right: 0.15rem;
}

.status-time {
  font-size: 0.72rem;
  color: var(--muted);
}
</style>
