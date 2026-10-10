<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiJson } from '@/api/client'

interface AdminUser {
  id: string
  username: string
  email: string | null
  is_admin: boolean
  account_status: string
  created_at: string
}

const users = ref<AdminUser[]>([])
const loading = ref(false)

const statusText: Record<string, string> = {
  pending: '待审批',
  active: '已启用',
  disabled: '已禁用',
}

async function load() {
  loading.value = true
  try {
    users.value = await apiJson<AdminUser[]>('/api/auth/users')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '用户加载失败')
  } finally {
    loading.value = false
  }
}

async function act(row: AdminUser | Record<string, unknown>, action: 'approve' | 'enable' | 'disable') {
  const user = row as AdminUser
  try {
    await apiJson(`/api/auth/users/${user.id}/${action}`, { method: 'POST' })
    ElMessage.success('已更新')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作失败')
  }
}

async function toggleAdmin(row: AdminUser | Record<string, unknown>) {
  const user = row as AdminUser
  try {
    await apiJson(`/api/auth/users/${user.id}`, {
      method: 'PATCH',
      data: { is_admin: !user.is_admin },
    })
    await load()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '操作失败')
  }
}

async function resetPassword(row: AdminUser | Record<string, unknown>) {
  const user = row as AdminUser
  try {
    const { value } = await ElMessageBox.prompt(`为 ${user.username} 设置新密码`, '重置密码', {
      inputType: 'password',
      inputPlaceholder: '至少 6 位',
      confirmButtonText: '保存',
    })
    if (!value || value.length < 6) {
      ElMessage.warning('新密码至少 6 位')
      return
    }
    await apiJson(`/api/auth/users/${user.id}/password`, {
      method: 'POST',
      data: { new_password: value },
    })
    ElMessage.success('密码已重置，该用户需要重新登录')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error instanceof Error ? error.message : '重置失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page-card admin-users">
    <div class="section-head">
      <div>
        <h1>用户管理</h1>
        <p>审批新注册、启用或禁用账号、设置管理员，以及重置密码。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table v-loading="loading" :data="users" size="small">
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column prop="email" label="邮箱" min-width="180">
        <template #default="{ row }">{{ row.email || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">{{ statusText[row.account_status] || row.account_status }}</template>
      </el-table-column>
      <el-table-column label="管理员" width="90">
        <template #default="{ row }">{{ row.is_admin ? '是' : '否' }}</template>
      </el-table-column>
      <el-table-column label="注册时间" min-width="170">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="280">
        <template #default="{ row }">
          <el-button v-if="row.account_status === 'pending'" text type="primary" @click="act(row, 'approve')">审批通过</el-button>
          <el-button v-if="row.account_status === 'disabled'" text type="primary" @click="act(row, 'enable')">启用</el-button>
          <el-button v-if="row.account_status !== 'disabled'" text type="warning" @click="act(row, 'disable')">禁用</el-button>
          <el-button text @click="toggleAdmin(row)">{{ row.is_admin ? '取消管理员' : '设为管理员' }}</el-button>
          <el-button text @click="resetPassword(row)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped lang="scss">
.admin-users { padding: 1.2rem; }
h1 { margin: 0 0 0.25rem; font-size: 1.3rem; }
p { margin: 0; color: var(--muted); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }
</style>
