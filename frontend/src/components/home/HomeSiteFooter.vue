<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ALL_NAV_ITEMS } from '@/utils/platform'

const router = useRouter()

const links = ALL_NAV_ITEMS.filter((item) => item.id !== 'home')
</script>

<template>
  <footer class="site-footer">
    <div class="landing-container site-footer__inner">
      <div class="site-footer__brand">
        <strong>{{ links.length }}+ 计算模块</strong>
        <p>从结构预测到 MD 验证，点击即可进入对应工作区。</p>
      </div>
      <div class="site-footer__links">
        <button
          v-for="item in links"
          :key="item.id"
          type="button"
          class="site-footer__link"
          @click="router.push(`${item.path}/new`)"
        >
          {{ item.label }}
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </div>
  </footer>
</template>

<style scoped lang="scss">
.site-footer {
  background: linear-gradient(180deg, #f8fafc 0%, #eef4f8 100%);
  border-top: 1px solid var(--border);
  padding: 2.5rem 0 2rem;
}

.site-footer__inner {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.site-footer__brand {
  strong {
    font-size: 1.05rem;
    color: var(--title);
  }

  p {
    margin: 0.35rem 0 0;
    font-size: 0.84rem;
    color: var(--muted);
  }
}

.site-footer__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.site-footer__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.45rem 0.85rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--bio-blue-dark);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.4);
    background: var(--bio-green-light);
  }
}
</style>
