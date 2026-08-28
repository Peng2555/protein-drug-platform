<script setup lang="ts">
import { Connection, Cpu, Lock } from '@element-plus/icons-vue'

const features = [
  {
    icon: Connection,
    title: '统一入口',
    desc: 'Boltz2、Rosetta、ProteinMPNN、Vina、GROMACS 等工具在同一平台调用，不用分别部署。',
  },
  {
    icon: Cpu,
    title: 'GPU 并行',
    desc: '折叠与 MD 任务自动排队调度，多卡并行，批量突变体预测不再手工盯进程。',
  },
  {
    icon: Lock,
    title: '数据内网',
    desc: '任务与结构文件留在百奥内网环境，输入输出由团队账号隔离管理。',
  },
]
</script>

<template>
  <section class="feature-strip">
    <div class="landing-container feature-strip__grid">
      <article v-for="f in features" :key="f.title" class="feature-card">
        <div class="feature-card__icon">
          <el-icon :size="22"><component :is="f.icon" /></el-icon>
        </div>
        <h3>{{ f.title }}</h3>
        <p>{{ f.desc }}</p>
      </article>
    </div>
  </section>
</template>

<style scoped lang="scss">
.feature-strip {
  margin-top: -1.5rem;
  position: relative;
  z-index: 2;
  padding-bottom: 0.5rem;
}

.feature-strip__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.feature-card {
  padding: 1.35rem 1.4rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid var(--border);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
  transition: transform 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    transform: translateY(-3px);
    box-shadow: 0 18px 48px rgba(15, 23, 42, 0.1);
  }

  h3 {
    margin: 0.85rem 0 0.35rem;
    font-size: 1rem;
    color: var(--title);
  }

  p {
    margin: 0;
    font-size: 0.84rem;
    line-height: 1.65;
    color: var(--muted);
  }
}

.feature-card__icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: var(--bio-green-dark);
  background: linear-gradient(135deg, var(--bio-green-light), var(--bio-blue-light));
}
</style>
