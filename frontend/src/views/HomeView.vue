<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchJobs } from '@/api/jobs'
import type { Job } from '@/api/types'
import CapabilityMap from '@/components/home/CapabilityMap.vue'
import HomeProductPreview from '@/components/home/HomeProductPreview.vue'
import HomeFeatureStrip from '@/components/home/HomeFeatureStrip.vue'
import HomeFeaturesShowcase from '@/components/home/HomeFeaturesShowcase.vue'
import HomeHero from '@/components/home/HomeHero.vue'
import PlatformStatusBar from '@/components/home/PlatformStatusBar.vue'
import HomeRecentTasks from '@/components/home/HomeRecentTasks.vue'
import HomeSiteFooter from '@/components/home/HomeSiteFooter.vue'
import ScenarioShowcase from '@/components/home/ScenarioShowcase.vue'
import WorkflowCards from '@/components/home/WorkflowCards.vue'
import { WORKFLOWS_BY_SCENARIO, type ScenarioId } from '@/config/workflows'
import { useModuleJobsStore } from '@/stores/moduleJobs'
import { engineLabel } from '@/utils/constants'

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
const route = useRoute()
const moduleJobs = useModuleJobsStore()
const recentItems = ref<RecentItem[]>([])
const loadingRecent = ref(false)
const activeScenario = ref<ScenarioId>('vhh')

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
  if (route.hash) {
    setTimeout(() => {
      document.getElementById(route.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }
})
</script>

<template>
  <div class="landing">
    <HomeHero />

    <section class="landing-below-fold">
      <HomeFeatureStrip />
      <div class="landing-status" aria-label="平台运行状态">
        <div class="landing-container">
          <PlatformStatusBar />
        </div>
      </div>
    </section>

    <HomeFeaturesShowcase />

    <HomeProductPreview />

    <section id="scenarios" class="landing-section landing-section--soft landing-section--tight-top">
      <div class="landing-container">
        <div class="landing-section__head">
          <h2>按研发场景选择</h2>
          <p>切换场景查看推荐流程与能力模块，一键进入对应工作区。</p>
        </div>
        <ScenarioShowcase v-model="activeScenario" />
      </div>
    </section>

    <section id="workflows" class="landing-section">
      <div class="landing-container">
        <div class="landing-section__head landing-section__head--left">
          <h2>推荐工作流</h2>
          <p>每个场景下的常用流程，点按钮直接进入对应模块提交任务。</p>
        </div>
        <WorkflowCards :workflows="currentWorkflows" />
      </div>
    </section>

    <section id="capabilities" class="landing-section landing-section--soft">
      <div class="landing-container">
        <div class="landing-section__head">
          <h2>平台能力地图</h2>
          <p>搜索或浏览所有计算模块——主标题是你要做的事，小字是底层引擎。</p>
        </div>
        <CapabilityMap :scenario="activeScenario" />
      </div>
    </section>

    <section id="recent" class="landing-section">
      <div class="landing-container">
        <div class="landing-section__head landing-section__head--left">
          <div>
            <h2>最近任务</h2>
            <p>各模块最新提交，点击卡片进入详情继续分析。</p>
          </div>
          <el-button text type="primary" @click="router.push('/fold/tasks')">查看全部 →</el-button>
        </div>
        <HomeRecentTasks
          :items="recentItems"
          :loading="loadingRecent"
          @open="openRecent"
        />
      </div>
    </section>

    <HomeSiteFooter />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/home-landing.scss';

.landing {
  min-height: 100%;
  background: #fff;
}

.landing-below-fold {
  padding-top: clamp(2.5rem, 6vh, 4rem);
  border-top: 1px solid #f1f5f9;
  background: linear-gradient(180deg, #fafbfc 0%, #fff 120px);
}

.landing-status {
  padding: 0 0 2rem;
}

.landing-section__head--left {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
</style>
