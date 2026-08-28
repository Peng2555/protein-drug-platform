<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Menu } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { PLATFORM_NAME, ALL_NAV_ITEMS } from '@/utils/platform'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const menuOpen = ref(false)

const onHome = computed(() => route.name === 'home')

const navAnchors = [
  { id: 'features', label: '功能特性' },
  { id: 'scenarios', label: '研发场景' },
  { id: 'workflows', label: '工作流' },
  { id: 'capabilities', label: '能力地图' },
  { id: 'recent', label: '最近任务' },
]

function scrollTo(id: string) {
  menuOpen.value = false
  if (!onHome.value) {
    router.push({ name: 'home', hash: `#${id}` })
    return
  }
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function enterWorkbench() {
  router.push('/fold/new')
}

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <header class="landing-nav">
    <div class="landing-nav__inner landing-container">
      <RouterLink to="/home" class="landing-nav__brand">
        <img src="/assets/biocytogen-logo.png" alt="" class="landing-nav__logo" />
        <span>{{ PLATFORM_NAME }}</span>
      </RouterLink>

      <nav class="landing-nav__links" :class="{ open: menuOpen }">
        <button
          v-for="a in navAnchors"
          :key="a.id"
          type="button"
          class="landing-nav__link"
          @click="scrollTo(a.id)"
        >
          {{ a.label }}
        </button>
        <div class="landing-nav__dropdown">
          <span class="landing-nav__dropdown-label">模块</span>
          <div class="landing-nav__dropdown-panel">
            <button
              v-for="item in ALL_NAV_ITEMS.filter((i) => i.id !== 'home')"
              :key="item.id"
              type="button"
              @click="router.push(`${item.path}/new`)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </nav>

      <div class="landing-nav__actions">
        <span class="landing-nav__user">{{ auth.user?.username }}</span>
        <button type="button" class="landing-nav__btn landing-nav__btn--ghost" @click="onLogout">退出</button>
        <button type="button" class="landing-nav__btn landing-nav__btn--primary" @click="enterWorkbench">
          立即开始
          <el-icon><ArrowRight /></el-icon>
        </button>
        <button type="button" class="landing-nav__menu" aria-label="菜单" @click="menuOpen = !menuOpen">
          <el-icon :size="20"><Menu /></el-icon>
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped lang="scss">
.landing-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(14px);
}

.landing-nav__inner {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-height: 68px;
}

.landing-nav__brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  text-decoration: none;
  color: #0f172a;
  font-weight: 800;
  font-size: 0.98rem;
  letter-spacing: -0.02em;
  flex-shrink: 0;
}

.landing-nav__logo {
  height: 32px;
  width: auto;
}

.landing-nav__links {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex: 1;
  justify-content: center;

  @media (max-width: 900px) {
    display: none;
    position: absolute;
    top: 62px;
    left: 0;
    right: 0;
    flex-direction: column;
    align-items: stretch;
    padding: 0.75rem 1rem 1rem;
    background: #fff;
    border-bottom: 1px solid var(--border);
    box-shadow: var(--shadow-md);

    &.open {
      display: flex;
    }
  }
}

.landing-nav__link {
  padding: 0.45rem 0.85rem;
  border: none;
  background: transparent;
  font-size: 0.88rem;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;

  &:hover {
    color: #0f172a;
    background: #f8fafc;
  }
}

.landing-nav__dropdown {
  position: relative;

  &:hover .landing-nav__dropdown-panel {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
  }
}

.landing-nav__dropdown-label {
  padding: 0.45rem 0.85rem;
  font-size: 0.88rem;
  font-weight: 500;
  color: #64748b;
  cursor: default;
}

.landing-nav__dropdown-panel {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(6px);
  min-width: 160px;
  padding: 0.35rem;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  opacity: 0;
  visibility: hidden;
  transition: 0.15s ease;
  display: grid;
  gap: 0.15rem;

  button {
    padding: 0.45rem 0.65rem;
    border: none;
    background: transparent;
    text-align: left;
    font-size: 0.82rem;
    border-radius: 8px;
    cursor: pointer;
    color: var(--body);

    &:hover {
      background: var(--bg-soft);
      color: var(--bio-green-dark);
    }
  }
}

.landing-nav__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}

.landing-nav__user {
  font-size: 0.8rem;
  color: var(--muted);

  @media (max-width: 640px) {
    display: none;
  }
}

.landing-nav__btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.5rem 1rem;
  border-radius: 999px;
  font-size: 0.84rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
}

.landing-nav__btn--ghost {
  background: transparent;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.landing-nav__btn--primary {
  color: #fff;
  background: #0f172a;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.14);

  &:hover {
    background: #1e293b;
  }
}

.landing-nav__menu {
  display: none;
  padding: 0.35rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;

  @media (max-width: 900px) {
    display: grid;
    place-items: center;
  }
}
</style>
