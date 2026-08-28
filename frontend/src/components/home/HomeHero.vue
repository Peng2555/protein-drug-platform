<script setup lang="ts">
import { ArrowRight } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import PlatformStatusBar from '@/components/home/PlatformStatusBar.vue'
import {
  PLATFORM_NAME,
  PLATFORM_NAME_EN,
  PLATFORM_ORG,
  PLATFORM_TAGLINE,
} from '@/utils/platform'

const router = useRouter()
</script>

<template>
  <section class="home-hero">
    <div class="home-hero__bg" aria-hidden="true">
      <div class="home-hero__orb home-hero__orb--1" />
      <div class="home-hero__orb home-hero__orb--2" />
      <div class="home-hero__grid" />
    </div>

    <div class="landing-container home-hero__inner">
      <div class="home-hero__copy">
        <img src="/assets/biocytogen-logo.png" alt="" class="home-hero__logo" />
        <p class="home-hero__org">{{ PLATFORM_ORG }}</p>
        <h1>
          计算工具，助力
          <span class="home-hero__accent">蛋白与药物</span>
          研发
        </h1>
        <p class="home-hero__sub">{{ PLATFORM_NAME }} · {{ PLATFORM_NAME_EN }}</p>
        <p class="home-hero__lead">
          设计突变体、预测复合物结构、对接小分子并做 MD 验证。内网一站式部署，无需额外配置环境。
        </p>
        <div class="home-hero__actions">
          <button type="button" class="btn btn--primary" @click="router.push('/fold/new')">
            立即开始
            <el-icon><ArrowRight /></el-icon>
          </button>
          <button type="button" class="btn btn--ghost" @click="router.push('/fold/tasks')">
            查看我的任务
          </button>
        </div>
        <p class="home-hero__tag">{{ PLATFORM_TAGLINE }}</p>
      </div>

      <div class="home-hero__aside">
        <div class="home-hero__visual" aria-hidden="true">
          <div class="molecule">
            <span class="molecule__node molecule__node--a" />
            <span class="molecule__node molecule__node--b" />
            <span class="molecule__node molecule__node--c" />
            <span class="molecule__bond molecule__bond--1" />
            <span class="molecule__bond molecule__bond--2" />
            <span class="molecule__bond molecule__bond--3" />
          </div>
          <div class="visual-card visual-card--1">Boltz2</div>
          <div class="visual-card visual-card--2">Rosetta</div>
          <div class="visual-card visual-card--3">GROMACS</div>
        </div>
        <PlatformStatusBar class="home-hero__status" dark />
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.home-hero {
  position: relative;
  overflow: hidden;
  color: #fff;
  padding: 3.5rem 0 3rem;
  background: linear-gradient(135deg, #004d47 0%, #0a6e68 35%, #1a4a8a 100%);
}

.home-hero__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.home-hero__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.45;
}

.home-hero__orb--1 {
  width: 420px;
  height: 420px;
  top: -120px;
  right: 8%;
  background: #00d4c8;
}

.home-hero__orb--2 {
  width: 320px;
  height: 320px;
  bottom: -80px;
  left: 12%;
  background: #5b8fd9;
}

.home-hero__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, black, transparent 95%);
}

.home-hero__inner {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
  gap: 2.5rem;
  align-items: center;

  @media (max-width: 960px) {
    grid-template-columns: 1fr;
  }
}

.home-hero__logo {
  height: 36px;
  width: auto;
  margin-bottom: 1rem;
  filter: brightness(0) invert(1);
  opacity: 0.95;
}

.home-hero__org {
  margin: 0 0 0.5rem;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.72);
}

h1 {
  margin: 0;
  font-size: clamp(2rem, 4vw, 2.85rem);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.home-hero__accent {
  display: inline-block;
  background: linear-gradient(90deg, #7ff7ee, #a8c8ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.home-hero__sub {
  margin: 0.65rem 0 0;
  font-size: 0.88rem;
  color: rgba(255, 255, 255, 0.75);
}

.home-hero__lead {
  margin: 1.15rem 0 0;
  max-width: 34rem;
  font-size: 1.02rem;
  line-height: 1.75;
  color: rgba(255, 255, 255, 0.88);
}

.home-hero__tag {
  margin: 1.25rem 0 0;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.55);
}

.home-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.6rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.72rem 1.35rem;
  border-radius: 999px;
  font-size: 0.92rem;
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

.btn--primary {
  color: #0a4a45;
  background: #fff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);

  &:hover {
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
  }
}

.btn--ghost {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.35);
  backdrop-filter: blur(4px);

  &:hover {
    background: rgba(255, 255, 255, 0.16);
  }
}

.home-hero__aside {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.home-hero__visual {
  position: relative;
  min-height: 260px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(8px);
}

.molecule {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.molecule__node {
  position: absolute;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.5);
  background: rgba(127, 247, 238, 0.25);
}

.molecule__node--a {
  width: 56px;
  height: 56px;
  top: 38%;
  left: 42%;
}

.molecule__node--b {
  width: 40px;
  height: 40px;
  top: 52%;
  left: 58%;
}

.molecule__node--c {
  width: 32px;
  height: 32px;
  top: 30%;
  left: 58%;
}

.molecule__bond {
  position: absolute;
  height: 2px;
  background: rgba(255, 255, 255, 0.35);
  transform-origin: left center;
}

.molecule__bond--1 {
  width: 80px;
  top: 46%;
  left: 46%;
  transform: rotate(25deg);
}

.molecule__bond--2 {
  width: 64px;
  top: 40%;
  left: 50%;
  transform: rotate(-30deg);
}

.molecule__bond--3 {
  width: 52px;
  top: 48%;
  left: 52%;
  transform: rotate(55deg);
}

.visual-card {
  position: absolute;
  padding: 0.35rem 0.7rem;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.2);
  animation: float 4s ease-in-out infinite;
}

.visual-card--1 {
  top: 14%;
  left: 10%;
}

.visual-card--2 {
  top: 18%;
  right: 12%;
  animation-delay: 0.8s;
}

.visual-card--3 {
  bottom: 16%;
  left: 16%;
  animation-delay: 1.6s;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-6px);
  }
}
</style>
