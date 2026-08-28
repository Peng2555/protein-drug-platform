<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  FEATURE_TABS,
  formatFeatureBullet,
  type FeatureTabId,
} from '@/config/homeFeatures'

const router = useRouter()
const activeTab = ref<FeatureTabId>('antibody')

const tabs = FEATURE_TABS

function setTab(id: FeatureTabId) {
  activeTab.value = id
}

function currentTab() {
  return tabs.find((t) => t.id === activeTab.value) ?? tabs[0]
}

function go(route: string) {
  router.push(route)
}
</script>

<template>
  <section id="features" class="features-showcase">
    <div class="landing-container">
      <div class="features-panel">
        <header class="features-panel__head">
          <p class="features-panel__eyebrow">Features</p>
          <h2>了解平台能为你做什么</h2>
        </header>

        <div class="features-panel__tabs" role="tablist" aria-label="研发方向">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            role="tab"
            class="features-panel__tab"
            :class="{ 'features-panel__tab--active': activeTab === tab.id }"
            :aria-selected="activeTab === tab.id"
            @click="setTab(tab.id)"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="features-panel__body">
          <Transition name="feature-pane" mode="out-in">
            <div :key="activeTab" class="features-pane">
              <div class="features-pane__visual">
                <img
                  :src="currentTab().image"
                  :alt="currentTab().imageAlt"
                  loading="lazy"
                />
              </div>

              <article class="features-pane__card">
                <h3>{{ currentTab().title }}</h3>
                <ul>
                  <li
                    v-for="(bullet, i) in currentTab().bullets"
                    :key="i"
                    v-html="formatFeatureBullet(bullet.text)"
                  />
                </ul>
                <button
                  type="button"
                  class="features-pane__cta"
                  @click="go(currentTab().ctaRoute)"
                >
                  {{ currentTab().ctaLabel }}
                  <el-icon><ArrowRight /></el-icon>
                </button>
              </article>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.features-showcase {
  padding: clamp(2.5rem, 5vh, 4rem) 0;
  background: #fff;
}

.features-panel {
  border: 1px solid #e5e7eb;
  border-radius: 24px;
  background: #fff;
  padding: clamp(2rem, 4vw, 3rem) clamp(1.5rem, 3vw, 2.5rem)
    clamp(1.75rem, 3vw, 2.5rem);
}

.features-panel__head {
  text-align: center;
  margin-bottom: clamp(1.5rem, 2.5vw, 2rem);
}

.features-panel__eyebrow {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #0d9488;
}

.features-panel__head h2 {
  margin: 0.5rem 0 0;
  font-size: clamp(1.65rem, 3.2vw, 2.25rem);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.2;
  color: #111827;
}

.features-panel__tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.6rem;
  margin-bottom: clamp(1.75rem, 3vw, 2.5rem);
}

.features-panel__tab {
  padding: 0.62rem 1.35rem;
  border: none;
  border-radius: 999px;
  font-size: 0.92rem;
  font-weight: 600;
  color: #374151;
  background: #f3f4f6;
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease;

  &:hover:not(.features-panel__tab--active) {
    background: #e5e7eb;
  }

  &--active {
    color: #fff;
    background: #111827;
  }
}

.features-panel__body {
  min-height: 400px;
}

.features-pane {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: clamp(1.5rem, 3vw, 3rem);
  align-items: center;

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
    gap: 1.75rem;
  }
}

.features-pane__visual {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  padding: 0.25rem 0.5rem;

  img {
    width: 100%;
    max-width: min(540px, 100%);
    max-height: 460px;
    object-fit: contain;
    mix-blend-mode: multiply;
    opacity: 0.98;
  }
}

.features-pane__card {
  padding: clamp(1.5rem, 2.5vw, 2rem);
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  background: #fff;

  h3 {
    margin: 0 0 1.15rem;
    font-size: clamp(1.1rem, 2vw, 1.35rem);
    font-weight: 800;
    line-height: 1.45;
    letter-spacing: -0.02em;
    color: #111827;
  }

  ul {
    margin: 0;
    padding-left: 1.15rem;
    list-style: disc;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }

  li {
    font-size: 0.9rem;
    line-height: 1.65;
    color: #4b5563;
    padding-left: 0.15rem;

    &::marker {
      color: #111827;
    }

    :deep(strong) {
      color: #111827;
      font-weight: 700;
    }
  }
}

.features-pane__cta {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 1.5rem;
  padding: 0.7rem 1.25rem;
  border: 1px solid #d1d5db;
  border-radius: 999px;
  font-size: 0.88rem;
  font-weight: 600;
  color: #111827;
  background: #fff;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background: #f9fafb;
    border-color: #9ca3af;
  }
}

.feature-pane-enter-active,
.feature-pane-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}

.feature-pane-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.feature-pane-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
