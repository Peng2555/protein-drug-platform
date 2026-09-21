<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  addProjectMember,
  fetchProjectMembers,
  updateAntibodyProject,
  type AntibodyProject,
  type ProjectMember,
} from '@/api/antibodyProjects'

const props = defineProps<{ project: AntibodyProject }>()
const emit = defineEmits<{ updated: [project: AntibodyProject] }>()
const members = ref<ProjectMember[]>([])
const showMember = ref(false)
const saving = ref(false)
const memberForm = reactive({ username: '', role: 'viewer' })

const statuses = [
  ['initiated', '立项'],
  ['design', '设计'],
  ['computation', '计算'],
  ['synthesis', '合成'],
  ['experiment', '实验'],
  ['completed', '完成'],
  ['paused', '暂停'],
  ['archived', '归档'],
]

async function loadMembers() {
  try {
    members.value = await fetchProjectMembers(props.project.id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '成员加载失败')
  }
}

async function changeStatus(status: string) {
  try {
    const updated = await updateAntibodyProject(props.project.id, { status })
    emit('updated', updated)
    ElMessage.success('项目阶段已更新')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新失败')
  }
}

async function submitMember() {
  if (!memberForm.username.trim()) return
  saving.value = true
  try {
    await addProjectMember(props.project.id, {
      username: memberForm.username.trim(),
      role: memberForm.role,
    })
    showMember.value = false
    memberForm.username = ''
    await loadMembers()
    ElMessage.success('成员已添加')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '添加失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadMembers)
</script>

<template>
  <div class="overview-grid">
    <section class="page-card overview-card">
      <div class="section-head">
        <div>
          <h2>项目信息</h2>
          <p>{{ project.project_code }}</p>
        </div>
      </div>
      <dl>
        <dt>靶点</dt><dd>{{ project.target_name }}</dd>
        <dt>说明</dt><dd>{{ project.description || '暂无说明' }}</dd>
        <dt>创建时间</dt><dd>{{ new Date(project.created_at).toLocaleString('zh-CN') }}</dd>
      </dl>
    </section>

    <section class="page-card overview-card">
      <div class="section-head">
        <div>
          <h2>当前阶段</h2>
          <p>手工调整项目所处研发阶段</p>
        </div>
      </div>
      <el-select :model-value="project.status" style="width: 100%" @change="changeStatus">
        <el-option v-for="[value, label] in statuses" :key="value" :label="label" :value="value" />
      </el-select>
    </section>

    <section class="page-card overview-card overview-card--members">
      <div class="section-head">
        <div>
          <h2>项目成员</h2>
          <p>负责人、可编辑成员和只读成员</p>
        </div>
        <el-button size="small" @click="showMember = true">添加成员</el-button>
      </div>
      <el-table :data="members" size="small">
        <el-table-column prop="username" label="用户" />
        <el-table-column label="权限" width="120">
          <template #default="{ row }">
            {{ row.role === 'owner' ? '负责人' : row.role === 'editor' ? '可编辑' : '只读' }}
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="showMember" title="添加项目成员" width="440px">
      <el-form label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="memberForm.username" />
        </el-form-item>
        <el-form-item label="权限">
          <el-radio-group v-model="memberForm.role">
            <el-radio value="editor">可编辑</el-radio>
            <el-radio value="viewer">只读</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showMember = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitMember">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/antibody-projects.scss';

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.overview-card { padding: 1rem; }
.overview-card--members { grid-column: 1 / -1; }

dl {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 0.55rem;
  margin: 0;
  font-size: 0.86rem;
}
dt { color: var(--muted); }
dd { margin: 0; color: var(--body); }

@media (max-width: 760px) {
  .overview-grid { grid-template-columns: 1fr; }
}
</style>
