<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchAntibodyProject, type AntibodyProject } from '@/api/antibodyProjects'
import { useAuthStore } from '@/stores/auth'
import AuditPanel from './AuditPanel.vue'
import ExperimentPanel from './ExperimentPanel.vue'
import ProjectOverviewPanel from './ProjectOverviewPanel.vue'
import ProjectResourcesPanel from './ProjectResourcesPanel.vue'
import VersionComparePanel from './VersionComparePanel.vue'
import VersionWorkspace from './VersionWorkspace.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const project = ref<AntibodyProject | null>(null)
const loading = ref(false)
const activeTab = ref('versions')
const projectId = computed(() => String(route.params.projectId || ''))
const canManage = computed(() =>
  Boolean(auth.user?.is_admin || (project.value && auth.user?.id === project.value.owner_id)),
)

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
      <header class="project-hero">
        <button type="button" class="back-link" @click="router.push({ name: 'antibody-projects' })">
          ← 项目列表
        </button>
        <div class="project-title">
          <div class="project-title__text">
            <div class="project-title__meta">
              <span class="code-chip">{{ project.project_code }}</span>
              <span class="target-chip">{{ project.target_name }}</span>
            </div>
            <h1>{{ project.name }}</h1>
          </div>
          <span class="status-pill" :data-status="project.status">
            {{ statusText[project.status] || project.status }}
          </span>
        </div>

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
            :can-manage="canManage"
            @updated="project = $event"
          />
        </el-tab-pane>
        <el-tab-pane label="操作历史" name="audit">
          <AuditPanel v-if="activeTab === 'audit'" :project-id="projectId" />
        </el-tab-pane>
      </el-tabs>
      </header>
    </template>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.project-hero {
  padding: 0.15rem 0.15rem 0;
}
.back-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 0.8rem;
  cursor: pointer;

  &:hover { color: var(--bio-green-dark); }
}
.project-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.55rem;
  min-width: 0;

  h1 {
    margin: 0.45rem 0 0;
    color: var(--title);
    font-size: 1.4rem;
    line-height: 1.3;
    overflow-wrap: anywhere;
  }
}
.project-title__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}
.target-chip {
  color: var(--body);
  font-size: 0.8rem;
}
.project-tabs {
  min-width: 0;
  margin-top: 0.85rem;

  :deep(.el-tabs__header) {
    margin-bottom: 0;
  }
  :deep(.el-tabs__nav-wrap::after) {
    height: 1px;
    background: #e8eef3;
  }
  :deep(.el-tabs__item) {
    height: 42px;
    font-weight: 600;
  }
  :deep(.el-tabs__content) {
    overflow: visible;
    padding: 1rem 0 0.4rem;
  }
  :deep(.el-tab-pane) { overflow: visible; }
}
</style>
