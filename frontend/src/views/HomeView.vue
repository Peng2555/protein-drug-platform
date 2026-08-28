<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchJobs } from '@/api/jobs'
import type { Job } from '@/api/types'
import CapabilityMap from '@/components/home/CapabilityMap.vue'
import PlatformStatusBar from '@/components/home/PlatformStatusBar.vue'
import ScenarioTabs from '@/components/home/ScenarioTabs.vue'
import WorkflowCards from '@/components/home/WorkflowCards.vue'
import {
  SCENARIOS,
  WORKFLOWS_BY_SCENARIO,
  type ScenarioId,
} from '@/config/workflows'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import {
  PLATFORM_NAME,
  PLATFORM_NAME_EN,
  PLATFORM_ORG,
  PLATFORM_TAGLINE,
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
const activeScenario = ref<ScenarioId>('vhh')

const currentScenario = computed(
  () => SCENARIOS.find((s) => s.id === activeScenario.value) ?? SCENARIOS[0],
)
const currentWorkflows = computed(() => WORKFLOWS_BY_SCENARIO[activeScenario.value] ?? [])

function routeForEngine(engine?: string | null): string {
  if (!engine) return 'fold-task'
  if (engine === 'boltz2' || engine === 'esmfold2') return 'fold-task'
  if (engine === 'protein_mpnn') return 'design-task'
  if (engine === 'rosetta_interface_eval') return 'rosetta-task'
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
  if (engine === 'rosetta_interface_eval') return '结构评价'
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
      { jobs: moduleJobs.rosettaJobs as Job[], routeName: 'rosetta-task', kind: '结构评价' },
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
      <div class="home-hero__main">
        <p class="home-hero__kicker">{{ PLATFORM_ORG }}</p>
        <h1>从序列到候选分子，一条工作流跑通</h1>
        <p class="home-hero__en">{{ PLATFORM_NAME }} · {{ PLATFORM_NAME_EN }}</p>
        <p class="home-hero__lead">
          结构预测、突变评价、序列设计、对接与 MD — 内网部署，按研发场景选择推荐流程即可开始。
        </p>
        <p class="home-hero__tag">{{ PLATFORM_TAGLINE }}</p>
        <div class="home-hero__actions">
          <el-button type="primary" size="large" @click="router.push('/fold/new')">
            开始结构预测
          </el-button>
          <el-button size="large" plain @click="router.push('/rosetta/new')">
            结构评价
          </el-button>
        </div>
      </div>
      <PlatformStatusBar class="home-hero__status" />
    </section>

    <section class="home-section">
      <div class="home-section__head">
        <div>
          <h2>按研发场景选择</h2>
          <p>切换场景查看推荐工作流与相关能力模块。</p>
        </div>
      </div>
      <ScenarioTabs v-model="activeScenario" :scenarios="SCENARIOS" />
      <div class="scenario-brief">
        <h3>{{ currentScenario.headline }}</h3>
        <p>{{ currentScenario.summary }}</p>
      </div>
    </section>

    <section class="home-section">
      <div class="home-section__head">
        <div>
          <h2>推荐工作流</h2>
          <p>{{ currentScenario.label }}场景下的常用流程，点击即可进入对应模块。</p>
        </div>
      </div>
      <WorkflowCards :workflows="currentWorkflows" />
    </section>

    <section class="home-section">
      <div class="home-section__head">
        <div>
          <h2>平台能力地图</h2>
          <p>浏览或搜索各计算模块，主标题是目标，副标题是底层引擎。</p>
        </div>
      </div>
      <CapabilityMap :scenario="activeScenario" />
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
          description="暂无任务，从上方推荐工作流任选一个开始吧"
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
            <el-tag
              size="small"
              :type="item.status === 'done' ? 'success' : item.status === 'failed' ? 'danger' : 'info'"
            >
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
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.8rem 1.9rem;
  overflow: hidden;
  background:
    radial-gradient(ellipse 60% 90% at 0% 0%, rgba(0, 172, 161, 0.14), transparent 55%),
    radial-gradient(ellipse 50% 80% at 100% 20%, rgba(46, 90, 165, 0.12), transparent 50%),
    linear-gradient(135deg, #f7fcfb 0%, #ffffff 45%, #f3f7fc 100%);
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
  font-size: clamp(1.65rem, 2.8vw, 2.05rem);
  color: var(--title);
  letter-spacing: -0.03em;
  line-height: 1.25;
}

.home-hero__en {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.home-hero__lead {
  margin: 0.95rem 0 0;
  max-width: 42rem;
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

.scenario-brief {
  margin-top: 1rem;
  padding: 0.85rem 1rem;
  border-radius: 12px;
  border: 1px solid rgba(0, 172, 161, 0.15);
  background: rgba(230, 247, 246, 0.45);

  h3 {
    margin: 0;
    font-size: 0.95rem;
    color: var(--title);
  }

  p {
    margin: 0.35rem 0 0;
    font-size: 0.82rem;
    line-height: 1.55;
    color: var(--body);
  }
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
