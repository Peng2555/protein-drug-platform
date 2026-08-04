<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeModule = computed(() => {
  if (route.path.startsWith('/md')) return 'md'
  if (route.path.startsWith('/maturation')) return 'maturation'
  return 'fold'
})

function goModule(mod: 'fold' | 'md' | 'maturation') {
  if (mod === 'md') router.push('/md')
  else if (mod === 'maturation') router.push('/maturation')
  else router.push('/fold')
}

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout-root">
    <div class="bg-pattern" aria-hidden="true" />
    <header class="site-header">
      <div class="header-accent" aria-hidden="true" />
      <div class="header-inner">
        <div class="brand-row">
          <a
            class="brand-link"
            href="https://biocytogen.com.cn/"
            target="_blank"
            rel="noopener noreferrer"
            title="百奥赛图官网"
          >
            <img src="/assets/biocytogen-logo.png" alt="百奥赛图 Biocytogen" class="brand-logo" />
          </a>
          <div class="brand-divider" aria-hidden="true" />
          <RouterLink to="/fold" class="product-brand">
            <span class="product-name">BoltzFold</span>
            <span class="product-tagline">结构预测 · 亲和力成熟 · MD 验证</span>
          </RouterLink>
        </div>

        <nav class="module-tabs" aria-label="功能模块">
          <button
            type="button"
            class="module-tab"
            :class="{ active: activeModule === 'fold' }"
            @click="goModule('fold')"
          >
            <span class="module-tab-icon">⬡</span>
            结构预测
          </button>
          <button
            type="button"
            class="module-tab"
            :class="{ active: activeModule === 'maturation' }"
            @click="goModule('maturation')"
          >
            <span class="module-tab-icon">◆</span>
            亲和力成熟
          </button>
          <button
            type="button"
            class="module-tab"
            :class="{ active: activeModule === 'md' }"
            @click="goModule('md')"
          >
            <span class="module-tab-icon">◎</span>
            MD 验证
          </button>
        </nav>

        <div class="user-bar">
          <span class="user-pill">
            <span class="user-dot" />
            <span class="username">{{ auth.user?.username }}</span>
          </span>
          <el-button size="small" plain class="logout-btn" @click="onLogout">退出</el-button>
        </div>
      </div>
    </header>

    <main class="layout-main">
      <RouterView />
    </main>

    <footer class="site-footer">
      <span>© 百奥赛图 Biocytogen</span>
      <span class="footer-tagline">从靶点到治疗药物 · Your Partner from Targets to Therapeutics</span>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.layout-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
}

.bg-pattern {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    radial-gradient(ellipse 70% 50% at 0% 0%, rgba(0, 172, 161, 0.08), transparent 55%),
    radial-gradient(ellipse 50% 40% at 100% 0%, rgba(46, 90, 165, 0.07), transparent 50%),
    radial-gradient(ellipse 40% 30% at 50% 100%, rgba(0, 172, 161, 0.04), transparent 60%),
    linear-gradient(180deg, #fafcfd 0%, var(--bg) 100%);
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 8px rgba(35, 35, 47, 0.04);
}

.header-accent {
  height: 3px;
  background: linear-gradient(90deg, var(--bio-green), var(--bio-blue));
}

.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1680px;
  margin: 0 auto;
  padding: 0.7rem 1.5rem;
  gap: 1rem;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-width: 0;
}

.brand-link {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.brand-logo {
  height: 38px;
  width: auto;
  display: block;
}

.brand-divider {
  width: 1px;
  height: 34px;
  background: var(--border-strong);
  flex-shrink: 0;
}

.product-brand {
  display: flex;
  flex-direction: column;
  min-width: 0;
  color: inherit;
  text-decoration: none;
}

.product-name {
  font-size: 1.08rem;
  font-weight: 700;
  color: var(--title);
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.product-tagline {
  font-size: 0.72rem;
  color: var(--muted);
  margin-top: 0.12rem;
}

.module-tabs {
  display: flex;
  gap: 0.4rem;
  padding: 0.25rem;
  background: var(--bg-soft);
  border-radius: 999px;
  border: 1px solid var(--border);
}

.module-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 0.4rem 0.95rem;
  border-radius: 999px;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.module-tab-icon {
  font-size: 0.75rem;
  opacity: 0.75;
}

.module-tab:hover {
  color: var(--body);
  background: rgba(255, 255, 255, 0.7);
}

.module-tab.active {
  background: #fff;
  color: var(--bio-green-dark);
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(35, 35, 47, 0.08);
}

.user-bar {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  background: var(--bio-blue-light);
  border: 1px solid rgba(46, 90, 165, 0.12);
  font-size: 0.8rem;
  color: var(--bio-blue-dark);
}

.user-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--bio-green);
  box-shadow: 0 0 0 2px rgba(0, 172, 161, 0.25);
}

.username {
  font-weight: 500;
}

.logout-btn {
  border-color: var(--border);
}

.layout-main {
  flex: 1;
  position: relative;
  z-index: 1;
  max-width: 1680px;
  width: 100%;
  margin: 0 auto;
  padding: 1.15rem 1.5rem 2rem;
}

.site-footer {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.9rem 1.5rem;
  font-size: 0.72rem;
  color: var(--muted);
  border-top: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
}

.footer-tagline {
  opacity: 0.85;
}

@media (max-width: 900px) {
  .header-inner {
    flex-wrap: wrap;
  }

  .module-tabs {
    order: 3;
    width: 100%;
    justify-content: center;
  }
}
</style>
