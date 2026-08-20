<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PLATFORM_NAME, PLATFORM_NAME_EN, PLATFORM_ORG } from '@/utils/platform'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const tab = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')

async function submit() {
  error.value = ''
  success.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    if (tab.value === 'login') {
      await auth.login(username.value.trim(), password.value)
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
      router.replace(redirect)
    } else {
      const result = await auth.register(username.value.trim(), password.value)
      if (result.pending_approval) {
        success.value = result.message || '注册成功，请等待管理员审批后再登录'
        tab.value = 'login'
        password.value = ''
      } else {
        await auth.login(username.value.trim(), password.value)
        const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
        router.replace(redirect)
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : tab.value === 'login' ? '登录失败' : '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-hero">
      <div class="hero-inner">
        <img src="/assets/biocytogen-logo.png" alt="百奥赛图" class="hero-logo" />
        <p class="hero-org">{{ PLATFORM_ORG }}</p>
        <h1>{{ PLATFORM_NAME }}</h1>
        <p class="hero-en">{{ PLATFORM_NAME_EN }}</p>
        <p class="hero-lead">
          把结构预测、序列工程、分子对接与分子动力学放在同一条研发工作流里。
        </p>
        <ul class="hero-points">
          <li>
            <strong>结构计算</strong>
            <span>Boltz2 / ESMFold2 复合物折叠与 3D 分析</span>
          </li>
          <li>
            <strong>序列工程</strong>
            <span>可开发性评估、亲和力成熟与合成筛选</span>
          </li>
          <li>
            <strong>分子验证</strong>
            <span>全局对接与 GROMACS 显式溶剂模拟</span>
          </li>
        </ul>
      </div>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <h2>{{ tab === 'login' ? '登录平台' : '申请账号' }}</h2>
        <p class="auth-hint">注册后需管理员审批方可登录</p>

        <el-tabs v-model="tab" class="auth-tabs" @tab-change="() => { error = ''; success = '' }">
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
              :autocomplete="tab === 'login' ? 'current-password' : 'new-password'"
              placeholder="请输入密码"
            />
          </el-form-item>
          <el-alert
            v-if="success"
            :title="success"
            type="success"
            show-icon
            :closable="false"
            class="auth-notice"
          />
          <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="auth-notice" />
          <el-button type="primary" native-type="submit" :loading="loading" class="auth-submit" size="large">
            {{ tab === 'login' ? '进入平台' : '提交注册' }}
          </el-button>
        </el-form>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.auth-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(380px, 0.95fr);
}

.auth-hero {
  position: relative;
  display: flex;
  align-items: center;
  padding: 3.2rem 4rem;
  color: #f4fbff;
  background:
    radial-gradient(ellipse 70% 55% at 12% 8%, rgba(0, 172, 161, 0.35), transparent 58%),
    radial-gradient(ellipse 55% 45% at 90% 90%, rgba(46, 90, 165, 0.35), transparent 52%),
    linear-gradient(165deg, #163a6e 0%, #0f2c55 48%, #0b3d3a 100%);
}

.hero-inner {
  max-width: 520px;
}

.hero-logo {
  height: 42px;
  width: auto;
  background: #fff;
  border-radius: 10px;
  padding: 0.28rem 0.4rem;
}

.hero-org {
  margin: 1.1rem 0 0.35rem;
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  color: rgba(244, 251, 255, 0.72);
}

h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.25;
}

.hero-en {
  margin: 0.35rem 0 0;
  font-size: 0.86rem;
  color: rgba(244, 251, 255, 0.62);
}

.hero-lead {
  margin: 1.15rem 0 0;
  font-size: 0.95rem;
  line-height: 1.7;
  color: rgba(244, 251, 255, 0.86);
}

.hero-points {
  list-style: none;
  margin: 1.6rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.7rem;
}

.hero-points li {
  padding: 0.85rem 0.95rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.hero-points strong {
  font-size: 0.86rem;
}

.hero-points span {
  font-size: 0.78rem;
  color: rgba(244, 251, 255, 0.68);
}

.auth-panel {
  display: grid;
  place-items: center;
  padding: 2rem 1.5rem;
  background: var(--bg);
}

.auth-card {
  width: min(420px, 100%);
  padding: 1.8rem 1.7rem 1.6rem;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

h2 {
  margin: 0;
  font-size: 1.28rem;
  color: var(--title);
}

.auth-hint {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}

.auth-tabs {
  margin: 0.85rem 0 0.15rem;
}

.auth-notice {
  margin-bottom: 0.75rem;
}

.auth-submit {
  width: 100%;
  font-weight: 600;
}

@media (max-width: 900px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .auth-hero {
    padding: 2rem 1.4rem 1.6rem;
  }

  h1 {
    font-size: 1.55rem;
  }
}
</style>
