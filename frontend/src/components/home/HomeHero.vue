<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PLATFORM_TAGLINE } from '@/utils/platform'

const router = useRouter()

const rotateWords = ['抗体工程', '小分子药物发现', '多肽设计与发现']

const showcaseSlides = [
  {
    id: 'antibody',
    label: '抗体工程',
    image: '/assets/hero/antibody-engineering.png',
    alt: 'Herceptin（Trastuzumab）Fab 结合 HER2，PDB 1N8Z',
    route: '/fold/new',
  },
  {
    id: 'small-molecule',
    label: '小分子药物发现',
    image: '/assets/hero/small-molecule-discovery.png',
    alt: 'Imatinib（STI571）结合 Bcr-Abl 激酶，PDB 1IEP',
    route: '/docking/new',
  },
  {
    id: 'peptide',
    label: '多肽设计与发现',
    image: '/assets/hero/peptide-design.png',
    alt: '多肽表位结合 Rituximab Fab 片段',
    route: '/fold/new',
  },
] as const

const activeWordIndex = ref(0)
const activeSlide = computed(() => showcaseSlides[activeWordIndex.value] ?? showcaseSlides[0])

let rotateTimer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  rotateTimer = setInterval(() => {
    activeWordIndex.value = (activeWordIndex.value + 1) % rotateWords.length
  }, 3200)
})

onUnmounted(() => {
  if (rotateTimer) clearInterval(rotateTimer)
})

function goSlide(index: number) {
  activeWordIndex.value = index
}
</script>

<template>
  <section class="home-hero">
    <div class="home-hero__ambient" aria-hidden="true" />

    <div class="landing-container home-hero__inner">
      <div class="home-hero__copy">
        <h1 class="home-hero__headline">
          <span class="home-hero__line">计算工具助力于</span>
          <span class="home-hero__line home-hero__line--accent">
            <span class="home-hero__rotator" aria-live="polite">
              <Transition name="hero-word" mode="out-in">
                <span :key="rotateWords[activeWordIndex]" class="home-hero__accent">
                  {{ rotateWords[activeWordIndex] }}
                </span>
              </Transition>
            </span>
          </span>
        </h1>
        <p class="home-hero__lead">
          设计突变体、预测复合物结构、小分子设计、分子动力学模拟以及蛋白质能量计算。
        </p>
        <div class="home-hero__actions">
          <button type="button" class="btn btn--secondary" @click="router.push('/fold/tasks')">
            查看我的任务
          </button>
          <button type="button" class="btn btn--primary" @click="router.push('/fold/new')">
            立即开始
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
        <p class="home-hero__tag">{{ PLATFORM_TAGLINE }}</p>
      </div>

      <div class="home-hero__aside">
        <div class="hero-visual">
          <div class="hero-visual__stage">
            <div class="hero-visual__halo hero-visual__halo--1" aria-hidden="true" />
            <div class="hero-visual__halo hero-visual__halo--2" aria-hidden="true" />
            <div class="hero-visual__ring" aria-hidden="true" />

            <button
              type="button"
              class="hero-visual__frame"
              :aria-label="`${activeSlide.label} 结构示意`"
              @click="router.push(activeSlide.route)"
            >
              <Transition name="hero-image" mode="out-in">
                <figure :key="activeSlide.id" class="hero-visual__figure">
                  <img :src="activeSlide.image" :alt="activeSlide.alt" loading="lazy" />
                </figure>
              </Transition>
            </button>
          </div>

          <div class="hero-visual__dots" role="tablist" aria-label="切换展示主题">
            <button
              v-for="(slide, index) in showcaseSlides"
              :key="slide.id"
              type="button"
              role="tab"
              class="hero-visual__dot"
              :class="{ 'hero-visual__dot--active': index === activeWordIndex }"
              :aria-selected="index === activeWordIndex"
              :aria-label="slide.label"
              @click="goSlide(index)"
            />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.home-hero {
  position: relative;
  overflow: hidden;
  color: var(--title);
  min-height: calc(100dvh - 68px);
  display: flex;
  align-items: center;
  padding: clamp(2rem, 4vh, 3rem) 0;
  background: #fff;
}

.home-hero__ambient {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 50% 42% at 82% 38%, rgba(0, 172, 161, 0.09), transparent 72%),
    radial-gradient(ellipse 38% 32% at 16% 76%, rgba(91, 143, 217, 0.05), transparent 70%);
}

.home-hero__inner {
  position: relative;
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(380px, 1.18fr);
  gap: clamp(2rem, 4vw, 3.5rem);
  align-items: center;

  @media (max-width: 960px) {
    grid-template-columns: 1fr;
    gap: 2rem;
  }
}

.home-hero__copy {
  max-width: 36rem;
  width: 100%;
  margin-inline: auto;
  text-align: center;
}

.home-hero__headline {
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.home-hero__line {
  display: block;
  font-size: clamp(2.1rem, 4.5vw, 3.2rem);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.035em;
  color: #0f172a;

  &--accent {
    display: block;
    font-size: clamp(2rem, 4.4vw, 3.1rem);
    font-weight: 800;
    min-height: 1.15em;
  }
}

.home-hero__rotator {
  position: relative;
  display: inline-block;
  min-width: 8.5em;
  height: 1.15em;
  overflow: hidden;

  .home-hero__accent {
    position: absolute;
    left: 50%;
    bottom: 0;
    transform: translateX(-50%);
    white-space: nowrap;
  }
}

.home-hero__accent {
  display: inline-block;
  color: var(--bio-green-dark);
}

.hero-word-enter-active,
.hero-word-leave-active {
  transition:
    transform 0.45s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.35s ease;
}

.hero-word-enter-from {
  opacity: 0;
  transform: translate(-50%, 100%);
}

.hero-word-leave-to {
  opacity: 0;
  transform: translate(-50%, -100%);
}

.hero-word-enter-to,
.hero-word-leave-from {
  opacity: 1;
  transform: translate(-50%, 0);
}

.home-hero__lead {
  margin: 1.25rem auto 0;
  max-width: 28rem;
  font-size: clamp(0.94rem, 1.5vw, 1.02rem);
  line-height: 1.75;
  color: #64748b;
}

.home-hero__tag {
  margin: 1.35rem 0 0;
  font-size: 0.76rem;
  color: #94a3b8;
}

.home-hero__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 1.65rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.82rem 1.45rem;
  border-radius: 999px;
  font-size: 0.94rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition:
    transform 0.15s,
    box-shadow 0.15s,
    background 0.15s;

  &:hover {
    transform: translateY(-1px);
  }
}

.btn--secondary {
  color: #0f172a;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;

  &:hover {
    background: #e8edf3;
  }
}

.btn--primary {
  color: #fff;
  background: #0f172a;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.15);

  &:hover {
    background: #1e293b;
  }
}

.home-hero__aside {
  display: flex;
  justify-content: center;
  align-items: center;
}

.hero-visual {
  width: min(100%, 640px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.35rem;
}

.hero-visual__stage {
  position: relative;
  width: 100%;
  min-height: clamp(360px, 48vh, 540px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1.5rem, 3vw, 2.5rem);
}

.hero-visual__halo {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(48px);

  &--1 {
    width: min(88%, 520px);
    height: min(72%, 420px);
    background: radial-gradient(circle, rgba(0, 172, 161, 0.14) 0%, rgba(0, 172, 161, 0.04) 45%, transparent 72%);
  }

  &--2 {
    width: min(70%, 400px);
    height: min(55%, 320px);
    top: 18%;
    right: 6%;
    background: radial-gradient(circle, rgba(91, 143, 217, 0.1) 0%, transparent 68%);
  }
}

.hero-visual__ring {
  position: absolute;
  inset: 8% 4%;
  border-radius: 50%;
  border: 1px solid rgba(0, 172, 161, 0.08);
  pointer-events: none;
  mask-image: radial-gradient(circle, black 42%, transparent 70%);
}

.hero-visual__frame {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  max-width: 560px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1);

  &:hover {
    transform: translateY(-4px) scale(1.01);

    .hero-visual__figure img {
      opacity: 1;
    }
  }
}

.hero-visual__figure {
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: clamp(300px, 42vh, 480px);
  background: transparent;

  img {
    display: block;
    width: 100%;
    max-width: 560px;
    max-height: clamp(300px, 42vh, 480px);
    object-fit: contain;
    background: transparent;
    /* 白底 PNG 与页面背景融合：白色区域变透明感 */
    mix-blend-mode: multiply;
    opacity: 0.96;
    transition:
      opacity 0.35s ease,
      transform 0.35s ease;
    animation: hero-float 7s ease-in-out infinite;
  }
}

@keyframes hero-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.hero-visual__dots {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.85);
  border: 1px solid rgba(226, 232, 240, 0.9);
  backdrop-filter: blur(8px);
}

.hero-visual__dot {
  width: 6px;
  height: 6px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: #cbd5e1;
  cursor: pointer;
  transition:
    width 0.25s ease,
    background 0.25s ease,
    opacity 0.25s ease;

  &:hover:not(.hero-visual__dot--active) {
    background: #94a3b8;
  }

  &--active {
    width: 24px;
    background: linear-gradient(90deg, var(--bio-green), #0ea5e9);
  }
}

.hero-image-enter-active,
.hero-image-leave-active {
  transition:
    opacity 0.55s ease,
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.hero-image-enter-from {
  opacity: 0;
  transform: scale(0.94) translateY(12px);
}

.hero-image-leave-to {
  opacity: 0;
  transform: scale(1.03) translateY(-8px);
}

@media (max-width: 960px) {
  .home-hero {
    min-height: auto;
    padding: 2.5rem 0 2rem;
  }

  .hero-visual {
    max-width: 520px;
  }

  .hero-visual__stage {
    min-height: clamp(280px, 38vh, 400px);
  }

  .hero-visual__figure {
    min-height: clamp(240px, 34vh, 360px);

    img {
      max-height: clamp(240px, 34vh, 360px);
    }
  }
}
</style>
