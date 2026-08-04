<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const tab = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    if (tab.value === 'login') {
      await auth.login(username.value.trim(), password.value)
    } else {
      await auth.register(username.value.trim(), password.value)
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/fold'
    router.replace(redirect)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="bg-pattern" aria-hidden="true" />
    <div class="auth-card page-card page-card--accent">
      <div class="auth-logo-wrap">
        <img src="/assets/biocytogen-logo.png" alt="百奥赛图 Biocytogen" class="auth-logo" />
      </div>
      <div class="auth-header">
        <h1>BoltzFold</h1>
        <p class="auth-sub">蛋白结构预测与 MD 验证平台</p>
        <p class="auth-hint">百奥赛图内部工具 · Boltz2 / ESMFold2 折叠与 GROMACS MD 验证</p>
      </div>

      <el-tabs v-model="tab" class="auth-tabs">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>

      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="username" autocomplete="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="auth-error" />
        <el-button type="primary" native-type="submit" :loading="loading" class="auth-submit" size="large">
          {{ tab === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<style scoped lang="scss">
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem 1rem;
  position: relative;
}

.bg-pattern {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 70% 50% at 0% 0%, rgba(0, 172, 161, 0.1), transparent 55%),
    radial-gradient(ellipse 50% 40% at 100% 100%, rgba(46, 90, 165, 0.08), transparent 50%),
    linear-gradient(180deg, #fafcfd 0%, var(--bg) 100%);
}

.auth-card {
  position: relative;
  z-index: 1;
  width: min(440px, 100%);
  padding: 2rem 1.85rem 1.85rem;
  box-shadow: var(--shadow-lg);
}

.auth-logo-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.65rem;
  margin-bottom: 0.5rem;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--bio-blue-light), var(--bio-green-light));
}

.auth-logo {
  height: 42px;
  width: auto;
}

.auth-header {
  text-align: center;
  margin-bottom: 0.25rem;
}

h1 {
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  color: var(--title);
  letter-spacing: -0.02em;
}

.auth-sub {
  margin: 0.4rem 0 0;
  font-size: 0.88rem;
  color: var(--body);
}

.auth-hint {
  margin: 0.35rem 0 0;
  font-size: 0.72rem;
  color: var(--muted);
}

.auth-tabs {
  margin: 1rem 0 0.25rem;
}

.auth-error {
  margin-bottom: 0.75rem;
}

.auth-submit {
  width: 100%;
  margin-top: 0.25rem;
  font-weight: 600;
}
</style>
