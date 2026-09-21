<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchAntibodyProject, type AntibodyProject } from '@/api/antibodyProjects'
import AuditPanel from './AuditPanel.vue'
import ExperimentPanel from './ExperimentPanel.vue'
import ProjectOverviewPanel from './ProjectOverviewPanel.vue'
import ProjectResourcesPanel from './ProjectResourcesPanel.vue'
import VersionComparePanel from './VersionComparePanel.vue'
import VersionWorkspace from './VersionWorkspace.vue'

const route = useRoute()
const router = useRouter()
const project = ref<AntibodyProject | null>(null)
const loading = ref(false)
const activeTab = ref('versions')
const projectId = computed(() => String(route.params.projectId || ''))

const statusText: Record<string, string> = {
  initiated: '立项',
  design: '设计',
  computation: '计算',
  synthesis: '合成',
  experiment: '实验',
  completed: '完成',
  paused: '暂停',
  archived: '归档',
}

async function load() {
  loading.value = true
  try {
    project.value = await fetchAntibodyProject(projectId.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '项目加载失败')
    await router.push({ name: 'antibody-projects' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="antibody-project-page">
    <template v-if="project">
      <header class="project-head page-card">
        <el-button text @click="router.push({ name: 'antibody-projects' })">← 返回项目列表</el-button>
        <div class="project-title">
          <div>
            <p class="eyebrow">{{ project.project_code }} · {{ project.target_name }}</p>
            <h1>{{ project.name }}</h1>
          </div>
          <el-tag effect="plain" size="large">{{ statusText[project.status] || project.status }}</el-tag>
        </div>
      </header>

      <el-tabs v-model="activeTab" class="project-tabs">
        <el-tab-pane label="版本管理" name="versions">
          <VersionWorkspace :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="序列对比" name="compare">
          <VersionComparePanel v-if="activeTab === 'compare'" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="样品与实验" name="experiments">
          <ExperimentPanel v-if="activeTab === 'experiments'" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="任务与文件" name="resources">
          <ProjectResourcesPanel v-if="activeTab === 'resources'" :project-id="projectId" />
        </el-tab-pane>
        <el-tab-pane label="项目概览" name="overview">
          <ProjectOverviewPanel
            v-if="activeTab === 'overview'"
            :project="project"
            @updated="project = $event"
          />
        </el-tab-pane>
        <el-tab-pane label="操作历史" name="audit">
          <AuditPanel v-if="activeTab === 'audit'" :project-id="projectId" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.project-head {
  margin-bottom: 0.8rem;
  padding: 0.7rem 1rem 1rem;
}
.project-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.25rem 0.35rem 0;
  min-width: 0;

  h1 {
    margin: 0.1rem 0 0;
    color: var(--title);
    font-size: 1.45rem;
    overflow-wrap: anywhere;
  }
  p { margin: 0; }
  .el-tag { flex-shrink: 0; }
}
.project-tabs {
  min-width: 0;

  :deep(.el-tabs__header) {
    margin-bottom: 0.9rem;
    padding: 0 0.8rem;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  :deep(.el-tabs__content),
  :deep(.el-tab-pane) {
    overflow: visible;
  }
}
</style>
