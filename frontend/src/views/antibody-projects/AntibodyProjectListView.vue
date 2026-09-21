<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAntibodyProject,
  fetchAntibodyProjects,
  updateAntibodyProject,
  type AntibodyProject,
} from '@/api/antibodyProjects'

const router = useRouter()
const projects = ref<AntibodyProject[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreate = ref(false)
const showArchived = ref(false)
const form = reactive({
  project_code: '',
  name: '',
  target_name: '',
  description: '',
})

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
    projects.value = await fetchAntibodyProjects(showArchived.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '项目加载失败')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.project_code.trim() || !form.name.trim() || !form.target_name.trim()) {
    ElMessage.warning('请填写项目编号、名称和靶点')
    return
  }
  saving.value = true
  try {
    const project = await createAntibodyProject({
      project_code: form.project_code.trim(),
      name: form.name.trim(),
      target_name: form.target_name.trim(),
      description: form.description.trim() || undefined,
    })
    showCreate.value = false
    Object.assign(form, { project_code: '', name: '', target_name: '', description: '' })
    ElMessage.success('项目已创建')
    await router.push({ name: 'antibody-project-detail', params: { projectId: project.id } })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    saving.value = false
  }
}

async function archiveProject(project: AntibodyProject) {
  try {
    await ElMessageBox.confirm(
      `归档“${project.name}”后，它将从默认列表隐藏。是否继续？`,
      '归档项目',
      { type: 'warning', confirmButtonText: '确认归档', cancelButtonText: '取消' },
    )
    await updateAntibodyProject(project.id, { status: 'archived' })
    await load()
    ElMessage.success('项目已归档')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof Error ? error.message : '归档失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="project-list-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">研发项目</p>
        <h1>抗体改造项目</h1>
        <p>以靶点为项目，统一管理候选抗体、版本谱系、计算与实验结果。</p>
      </div>
      <div class="page-actions">
        <el-switch
          v-model="showArchived"
          inline-prompt
          active-text="含归档"
          inactive-text="隐藏归档"
          @change="load"
        />
        <el-button type="primary" @click="showCreate = true">新建项目</el-button>
      </div>
    </header>

    <section v-loading="loading" class="project-grid">
      <button
        v-for="project in projects"
        :key="project.id"
        type="button"
        class="project-card page-card"
        @click="router.push({ name: 'antibody-project-detail', params: { projectId: project.id } })"
      >
        <div class="project-card__top">
          <span class="project-code">{{ project.project_code }}</span>
          <div class="project-card__actions">
            <el-tag size="small" effect="plain">{{ statusText[project.status] || project.status }}</el-tag>
            <el-button
              v-if="project.status !== 'archived'"
              text
              size="small"
              type="warning"
              @click.stop="archiveProject(project)"
            >
              归档
            </el-button>
          </div>
        </div>
        <h2>{{ project.name }}</h2>
        <p class="target">靶点 · {{ project.target_name }}</p>
        <p class="description">{{ project.description || '暂无项目说明' }}</p>
        <span class="updated">更新于 {{ new Date(project.updated_at).toLocaleString('zh-CN') }}</span>
      </button>
      <el-empty v-if="!loading && !projects.length" description="还没有抗体改造项目">
        <el-button type="primary" @click="showCreate = true">创建第一个项目</el-button>
      </el-empty>
    </section>

    <el-dialog v-model="showCreate" title="新建抗体改造项目" width="560px">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="项目编号">
            <el-input v-model="form.project_code" placeholder="例如 EGFR-001" />
          </el-form-item>
          <el-form-item label="靶点">
            <el-input v-model="form.target_name" placeholder="例如 EGFR" />
          </el-form-item>
        </div>
        <el-form-item label="项目名称">
          <el-input v-model="form.name" placeholder="例如 EGFR 抗体亲和力优化" />
        </el-form-item>
        <el-form-item label="项目说明">
          <el-input v-model="form.description" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">创建项目</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.project-grid {
  min-height: 240px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.project-card {
  min-height: 220px;
  padding: 1.15rem;
  border: 1px solid var(--border);
  text-align: left;
  cursor: pointer;

  &:hover {
    border-color: var(--bio-green);
    transform: translateY(-1px);
  }

  h2 { margin: 1rem 0 0.25rem; font-size: 1.08rem; color: var(--title); }
  .target { margin: 0; color: var(--bio-green-dark); font-weight: 600; }
  .description { min-height: 44px; color: var(--body); }
  .updated { font-size: 0.72rem; color: var(--muted); }
}

.project-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.project-card__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.project-code {
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
  color: var(--muted);
}

@media (max-width: 1100px) {
  .project-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .project-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
