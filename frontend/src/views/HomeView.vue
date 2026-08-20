<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Aim,
  ArrowRight,
  Brush,
  Cpu,
  EditPen,
  Histogram,
  MagicStick,
  Timer,
} from '@element-plus/icons-vue'
import { fetchJobs } from '@/api/jobs'
import type { Job } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import {
  NAV_GROUPS,
  PLATFORM_NAME,
  PLATFORM_NAME_EN,
  PLATFORM_ORG,
  PLATFORM_TAGLINE,
  type ModuleId,
  type NavItem,
} from '@/utils/platform'
import { engineLabel, statusLabel } from '@/utils/constants'

type RecentItem = {
  id: string
  name: string
  status: string
  created_at: string
  kind: string
  routeName: string
  meta: string
}

const router = useRouter()
const moduleJobs = useModuleJobsStore()
const recentItems = ref<RecentItem[]>([])
const loadingRecent = ref(false)

const iconMap: Partial<Record<ModuleId, unknown>> = {
  fold: Cpu,
  design: Brush,
  developability: EditPen,
  maturation: MagicStick,
  synthesis: Histogram,
  docking: Aim,
  md: Timer,
}

const pillars = [
  {
    id: 'structure',
    label: '结构计算',
    title: '从序列到三维结构',
    desc: '用 Boltz2 / ESMFold2 预测蛋白与复合物结构，作为后续设计与筛选的起点。',
    image: '/home/home-structure.png',
    accent: 'teal',
    cta: { label: '开始结构预测', to: '/fold/new' },
  },
  {
    id: 'sequence',
    label: '序列与抗体',
    title: '序列设计与工程改造',
    desc: 'ProteinMPNN 设计、ESM-2 改造、亲和力成熟与合成候选筛选，覆盖抗体工程主流程。',
    image: '/home/home-sequence.png',
    accent: 'blue',
    cta: { label: '进入序列设计', to: '/design/new' },
  },
  {
    id: 'ligand',
    label: '小分子药物筛选',
    title: '对接筛选与 MD 验证',
    desc: '口袋引导盲对接快速评估配体，再用 GROMACS 显式溶剂模拟复核结合稳定性。',
    image: '/home/home-ligand.png',
    accent: 'cyan',
    cta: { label: '开始分子对接', to: '/docking/new' },
  },
] as const

const pillarModules = computed(() =>
  pillars.map((pillar) => {
    const group = NAV_GROUPS.find((g) => g.id === pillar.id)
    const items = (group?.items ?? []).map((item: NavItem) => ({
      ...item,
      icon: iconMap[item.id],
    }))
    return { ...pillar, items }
  }),
)

function routeForEngine(engine?: string | null): string {
  if (!engine) return 'fold-task'
  if (engine === 'boltz2' || engine === 'esmfold2') return 'fold-task'
  if (engine === 'protein_mpnn') return 'design-task'
  if (engine === 'esm2_developability') return 'developability-task'
  if (engine === 'iggm_maturation') return 'maturation-task'
  if (engine === 'synthesis_select') return 'synthesis-task'
  if (engine === 'small_molecule_docking' || engine === 'ras_tricomplex_docking') return 'docking-task'
  if (engine?.includes('md') || engine === 'gromacs_md') return 'md-task'
  return 'fold-task'
}

function kindForEngine(engine?: string | null): string {
  if (!engine) return '任务'
  if (engine === 'boltz2' || engine === 'esmfold2') return '结构预测'
  if (engine === 'protein_mpnn') return '序列设计'
  if (engine === 'esm2_developability') return '序列改造'
  if (engine === 'iggm_maturation') return '亲和力成熟'
  if (engine === 'synthesis_select') return '合成候选'
  if (engine === 'small_molecule_docking' || engine === 'ras_tricomplex_docking') return '分子对接'
  if (engine?.includes('md') || engine === 'gromacs_md') return 'MD 验证'
  return engineLabel(engine)
}

async function loadRecent() {
  loadingRecent.value = true
  try {
    const [foldData] = await Promise.all([
      fetchJobs(12, true).catch(() => ({ items: [] as Job[] })),
      moduleJobs.refreshAll().catch(() => undefined),
    ])
    const foldItems: RecentItem[] = (foldData.items ?? []).map((j) => ({
      id: j.id,
      name: j.name || j.id.slice(0, 8),
      status: j.status,
      created_at: j.created_at,
      kind: kindForEngine(j.engine),
      routeName: routeForEngine(j.engine),
      meta: [
        engineLabel(j.engine),
        j.total_length ? `${j.total_length} aa` : null,
        j.iptm != null ? `ipTM ${j.iptm.toFixed(3)}` : null,
      ]
        .filter(Boolean)
        .join(' · '),
    }))

    const moduleBuckets: Array<{ jobs: Job[]; routeName: string; kind: string }> = [
      { jobs: moduleJobs.designJobs as Job[], routeName: 'design-task', kind: '序列设计' },
      { jobs: moduleJobs.developabilityJobs as Job[], routeName: 'developability-task', kind: '序列改造' },
      { jobs: moduleJobs.maturationJobs as Job[], routeName: 'maturation-task', kind: '亲和力成熟' },
      { jobs: moduleJobs.synthesisJobs as Job[], routeName: 'synthesis-task', kind: '合成候选' },
      { jobs: moduleJobs.dockingJobs as Job[], routeName: 'docking-task', kind: '分子对接' },
      { jobs: moduleJobs.mdJobs as Job[], routeName: 'md-task', kind: 'MD 验证' },
    ]
    const otherItems: RecentItem[] = moduleBuckets.flatMap(({ jobs, routeName, kind }) =>
      jobs.map((j) => ({
        id: j.id,
        name: j.name || j.id.slice(0, 8),
        status: j.status,
        created_at: j.created_at,
        kind,
        routeName,
        meta: engineLabel(j.engine),
      })),
    )

    recentItems.value = [...foldItems, ...otherItems]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 8)
  } catch {
    recentItems.value = []
  } finally {
    loadingRecent.value = false
  }
}

function openRecent(item: RecentItem) {
  router.push({ name: item.routeName, params: { id: item.id } })
}

onMounted(() => {
  void loadRecent()
})
</script>

<template>
  <div class="home-page">
    <section class="home-hero page-card">
      <div class="home-hero__copy">
        <p class="home-hero__kicker">{{ PLATFORM_ORG }}</p>
        <h1>{{ PLATFORM_NAME }}</h1>
        <p class="home-hero__en">{{ PLATFORM_NAME_EN }}</p>
        <p class="home-hero__lead">
          结构预测、序列工程与小分子筛选贯通同一工作流，从靶点到候选分子逐步推进。
        </p>
        <p class="home-hero__tag">{{ PLATFORM_TAGLINE }}</p>
        <div class="home-hero__actions">
          <el-button type="primary" size="large" @click="router.push('/fold/new')">
            开始结构预测
          </el-button>
          <el-button size="large" plain @click="router.push('/docking/new')">
            分子对接
          </el-button>
        </div>
      </div>
      <div class="home-hero__flow" aria-hidden="true">
        <div v-for="(p, i) in pillars" :key="p.id" class="flow-step">
          <span class="flow-step__idx">{{ i + 1 }}</span>
          <div>
            <strong>{{ p.label }}</strong>
            <span>{{ p.title }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="home-section">
      <div class="home-section__head">
        <div>
          <h2>三大能力板块</h2>
          <p>按研发流程选择板块，进入后可在左侧导航提交任务与查看结果。</p>
        </div>
      </div>

      <div class="pillar-stack">
        <article
          v-for="pillar in pillarModules"
          :key="pillar.id"
          class="pillar-card"
          :class="`pillar-card--${pillar.accent}`"
        >
          <div class="pillar-card__visual">
            <img :src="pillar.image" :alt="pillar.label" loading="lazy" />
            <div class="pillar-card__badge">{{ pillar.label }}</div>
          </div>
          <div class="pillar-card__content">
            <h3>{{ pillar.title }}</h3>
            <p>{{ pillar.desc }}</p>
            <div class="pillar-card__modules">
              <button
                v-for="item in pillar.items"
                :key="item.id"
                type="button"
                class="module-chip"
                @click="router.push(`${item.path}/new`)"
              >
                <span class="module-chip__icon">
                  <el-icon :size="18"><component :is="item.icon" /></el-icon>
                </span>
                <span class="module-chip__text">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.hint }}</span>
                </span>
                <el-icon class="module-chip__arrow" :size="14"><ArrowRight /></el-icon>
              </button>
            </div>
            <el-button type="primary" plain @click="router.push(pillar.cta.to)">
              {{ pillar.cta.label }}
            </el-button>
          </div>
        </article>
      </div>
    </section>

    <section class="home-section">
      <div class="home-section__head">
        <div>
          <h2>最近提交任务</h2>
          <p>汇总各模块近期任务，点击即可进入详情。</p>
        </div>
        <el-button text type="primary" @click="router.push('/fold/tasks')">查看结构任务</el-button>
      </div>
      <div v-loading="loadingRecent" class="recent-panel page-card">
        <el-empty
          v-if="!loadingRecent && !recentItems.length"
          description="暂无任务，从上方三大板块任选一个开始提交吧"
        />
        <div v-else class="recent-list">
          <button
            v-for="item in recentItems"
            :key="`${item.routeName}-${item.id}`"
            type="button"
            class="recent-item"
            @click="openRecent(item)"
          >
            <div class="recent-item__main">
              <div class="recent-item__title">
                <el-tag size="small" effect="plain" type="info">{{ item.kind }}</el-tag>
                <strong>{{ item.name }}</strong>
              </div>
              <span>{{ item.meta }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</span>
            </div>
            <el-tag size="small" :type="item.status === 'done' ? 'success' : item.status === 'failed' ? 'danger' : 'info'">
              {{ statusLabel(item.status) }}
            </el-tag>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.home-page {
  display: flex;
  flex-direction: column;
  gap: 1.6rem;
}

.home-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(240px, 0.85fr);
  gap: 1.6rem;
  padding: 1.7rem 1.8rem;
  overflow: hidden;
  background:
    radial-gradient(ellipse 60% 90% at 0% 0%, rgba(0, 172, 161, 0.14), transparent 55%),
    radial-gradient(ellipse 50% 80% at 100% 20%, rgba(46, 90, 165, 0.12), transparent 50%),
    linear-gradient(135deg, #f7fcfb 0%, #ffffff 45%, #f3f7fc 100%);

  @media (max-width: 960px) {
    grid-template-columns: 1fr;
  }
}

.home-hero__kicker {
  margin: 0 0 0.35rem;
  font-size: 0.78rem;
  color: var(--bio-green-dark);
  font-weight: 700;
  letter-spacing: 0.02em;
}

h1 {
  margin: 0;
  font-size: clamp(1.55rem, 2.4vw, 1.9rem);
  color: var(--title);
  letter-spacing: -0.03em;
}

.home-hero__en {
  margin: 0.3rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.home-hero__lead {
  margin: 0.95rem 0 0;
  max-width: 38rem;
  font-size: 0.95rem;
  line-height: 1.7;
  color: var(--body);
}

.home-hero__tag {
  margin: 0.55rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}

.home-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 1.25rem;
}

.home-hero__flow {
  display: grid;
  gap: 0.7rem;
  align-content: center;
}

.flow-step {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.85rem 0.95rem;
  border-radius: 14px;
  border: 1px solid rgba(0, 172, 161, 0.16);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(6px);

  strong {
    display: block;
    font-size: 0.88rem;
    color: var(--title);
  }

  span:not(.flow-step__idx) {
    display: block;
    margin-top: 0.15rem;
    font-size: 0.74rem;
    color: var(--muted);
  }
}

.flow-step__idx {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green), var(--bio-blue));
}

.home-section__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.95rem;

  h2 {
    margin: 0;
    font-size: 1.12rem;
    color: var(--title);
  }

  p {
    margin: 0.3rem 0 0;
    font-size: 0.82rem;
    color: var(--muted);
  }
}

.pillar-stack {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.pillar-card {
  display: grid;
  grid-template-columns: minmax(220px, 0.95fr) minmax(0, 1.25fr);
  gap: 0;
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: #fff;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
  transition: transform 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 36px rgba(15, 23, 42, 0.07);
  }

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.pillar-card__visual {
  position: relative;
  min-height: 220px;
  background: #eef7f6;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.pillar-card__badge {
  position: absolute;
  left: 0.9rem;
  top: 0.9rem;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--bio-green-dark);
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(0, 172, 161, 0.22);
  backdrop-filter: blur(4px);
}

.pillar-card--blue .pillar-card__badge {
  color: var(--bio-blue-dark);
  border-color: rgba(46, 90, 165, 0.22);
}

.pillar-card--cyan .pillar-card__badge {
  color: #0f766e;
}

.pillar-card__content {
  padding: 1.25rem 1.35rem 1.35rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;

  h3 {
    margin: 0;
    font-size: 1.15rem;
    color: var(--title);
    letter-spacing: -0.02em;
  }

  > p {
    margin: 0;
    font-size: 0.88rem;
    line-height: 1.65;
    color: var(--muted);
  }
}

.pillar-card__modules {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.55rem;

  @media (max-width: 700px) {
    grid-template-columns: 1fr;
  }
}

.module-chip {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.7rem 0.75rem;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #f8fbfb;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;

  &:hover {
    border-color: rgba(0, 172, 161, 0.4);
    background: #fff;
    transform: translateY(-1px);
  }
}

.module-chip__icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: linear-gradient(135deg, var(--bio-green-light), var(--bio-blue-light));
  color: var(--bio-green-dark);
}

.module-chip__text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
  flex: 1;

  strong {
    font-size: 0.86rem;
    color: var(--title);
  }

  span {
    font-size: 0.7rem;
    color: var(--muted);
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

.module-chip__arrow {
  color: var(--muted);
  flex-shrink: 0;
}

.recent-panel {
  min-height: 140px;
  padding: 0.35rem 0.45rem;
}

.recent-list {
  display: flex;
  flex-direction: column;
}

.recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  width: 100%;
  padding: 0.85rem 0.9rem;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  text-align: left;
  cursor: pointer;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: var(--bg-soft);
  }
}

.recent-item__main {
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  min-width: 0;

  > span {
    font-size: 0.74rem;
    color: var(--muted);
  }
}

.recent-item__title {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;

  strong {
    font-size: 0.9rem;
    color: var(--title);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
