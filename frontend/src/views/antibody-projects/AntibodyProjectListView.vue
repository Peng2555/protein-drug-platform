<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAntibodyProject,
  deleteAntibodyProject,
  fetchAntibodyProjects,
  updateAntibodyProject,
  type AntibodyProject,
} from '@/api/antibodyProjects'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const projects = ref<AntibodyProject[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreate = ref(false)
const showEdit = ref(false)
const editing = ref<AntibodyProject | null>(null)
const showArchived = ref(false)
const keyword = ref('')
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

function compareProjectCode(left: string, right: string) {
  return left.localeCompare(right, 'en', { numeric: true, sensitivity: 'base' })
}

const visibleProjects = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  const rows = query
    ? projects.value.filter((project) =>
        [project.project_code, project.name, project.target_name, project.description || '']
          .some((value) => value.toLowerCase().includes(query)),
      )
    : projects.value
  return [...rows].sort((left, right) => compareProjectCode(left.project_code, right.project_code))
})

function formatUpdated(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
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

function canManage(project: AntibodyProject) {
  return Boolean(auth.user?.is_admin || auth.user?.id === project.owner_id)
}

function openEdit(project: AntibodyProject) {
  editing.value = project
  Object.assign(form, {
    project_code: project.project_code,
    name: project.name,
    target_name: project.target_name,
    description: project.description || '',
  })
  showEdit.value = true
}

async function saveEdit() {
  if (!editing.value) return
  if (!form.project_code.trim() || !form.name.trim() || !form.target_name.trim()) {
    ElMessage.warning('请填写项目编号、名称和靶点')
    return
  }
  saving.value = true
  try {
    await updateAntibodyProject(editing.value.id, {
      project_code: form.project_code.trim(),
      name: form.name.trim(),
      target_name: form.target_name.trim(),
      description: form.description.trim() || null,
    })
    showEdit.value = false
    ElMessage.success('项目已更新')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '修改失败')
  } finally {
    saving.value = false
  }
}

async function removeProject(project: AntibodyProject) {
  try {
    await ElMessageBox.confirm(
      `删除“${project.name}”后，候选抗体、版本和实验记录会一起删除，且不能恢复。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await deleteAntibodyProject(project.id)
    await load()
    ElMessage.success('项目已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="project-list-page">
    <header class="board-hero">
      <div>
        <p class="eyebrow">研发项目</p>
        <h1>抗体改造项目</h1>
        <p>候选、版本和实验放在同一个项目里往下看。</p>
      </div>
      <el-button type="primary" @click="showCreate = true">新建项目</el-button>
    </header>

    <div class="board-bar">
      <el-input
        v-model="keyword"
        class="project-search"
        clearable
        placeholder="搜索编号、名称或靶点"
      />
      <span class="list-count">{{ visibleProjects.length }} 个项目</span>
      <el-switch
        v-model="showArchived"
        inline-prompt
        active-text="含归档"
        inactive-text="隐藏归档"
        @change="load"
      />
    </div>

    <section v-loading="loading" class="project-grid">
      <article
        v-for="project in visibleProjects"
        :key="project.id"
        class="project-card"
      >
        <button
          type="button"
          class="project-card__body"
          @click="router.push({ name: 'antibody-project-detail', params: { projectId: project.id } })"
        >
          <span class="project-card__top">
            <span class="project-code">{{ project.project_code }}</span>
            <span class="status-pill" :data-status="project.status">
              {{ statusText[project.status] || project.status }}
            </span>
          </span>
          <h2>{{ project.name }}</h2>
          <p class="description">{{ project.description || '暂无项目说明' }}</p>
          <span class="project-card__meta">
            <span>靶点 {{ project.target_name }}</span>
            <time>{{ formatUpdated(project.updated_at) }}</time>
          </span>
        </button>
        <footer v-if="canManage(project)" class="project-card__foot">
          <button type="button" @click="openEdit(project)">修改</button>
          <button type="button" class="danger" @click="removeProject(project)">删除</button>
        </footer>
      </article>
      <el-empty
        v-if="!loading && !projects.length"
        class="project-empty"
        description="还没有抗体改造项目"
      >
        <el-button type="primary" @click="showCreate = true">创建第一个项目</el-button>
      </el-empty>
      <el-empty
        v-else-if="!loading && !visibleProjects.length"
        class="project-empty"
        description="没有符合搜索的项目"
      />
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

    <el-dialog v-model="showEdit" title="修改项目" width="560px">
      <el-form label-position="top">
        <el-form-item label="项目编号">
          <el-input v-model="form.project_code" placeholder="例如 EGFR-001" />
        </el-form-item>
        <el-form-item label="靶点">
          <el-input v-model="form.target_name" />
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="项目说明">
          <el-input v-model="form.description" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.board-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.1rem;

  h1 {
    margin: 0.15rem 0 0.2rem;
    color: var(--title);
    font-size: 1.7rem;
    font-weight: 680;
    letter-spacing: -0.03em;
  }
  p { margin: 0; color: var(--muted); }
}

.board-bar {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 0.9rem;
}

.project-search { width: 260px; }
.list-count { color: var(--muted); font-size: 0.78rem; }

.project-grid {
  min-height: 220px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 0.85rem;
}

.project-empty { grid-column: 1 / -1; }

.project-card {
  display: flex;
  flex-direction: column;
  min-height: 188px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(35, 35, 47, 0.04);
  overflow: hidden;

  &:hover {
    border-color: #b7e4e1;
    box-shadow: 0 8px 22px rgba(0, 122, 114, 0.08);
  }
}

.project-card__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.45rem;
  width: 100%;
  padding: 1rem 1rem 0.85rem;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;

  h2 {
    margin: 0.15rem 0 0;
    color: var(--title);
    font-size: 1.05rem;
    font-weight: 680;
    line-height: 1.4;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
  }
}

.project-card__top,
.project-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.project-code {
  font-family: var(--mono);
  font-size: 0.75rem;
  color: var(--bio-green-darkest);
}

.description {
  display: -webkit-box;
  margin: 0;
  min-height: 2.7em;
  overflow: hidden;
  color: var(--body);
  font-size: 0.84rem;
  line-height: 1.45;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.project-card__meta {
  margin-top: auto;
  padding-top: 0.35rem;
  color: var(--muted);
  font-size: 0.76rem;
}

.project-card__foot {
  display: flex;
  justify-content: flex-end;
  gap: 0.35rem;
  padding: 0.35rem 0.65rem;
  border-top: 1px solid #eef2f5;

  button {
    padding: 0.28rem 0.55rem;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: var(--bio-green-dark);
    font-size: 0.78rem;
    cursor: pointer;

    &:hover { background: var(--bio-green-light); }
    &.danger { color: #b42318; }
    &.danger:hover { background: #fdecec; }
  }
}

@media (max-width: 720px) {
  .board-hero { flex-direction: column; align-items: flex-start; }
  .board-bar { flex-wrap: wrap; }
  .project-search { width: 100%; }
}
</style>
