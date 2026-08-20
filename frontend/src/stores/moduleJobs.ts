import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchDesignJobs } from '@/api/design'
import { fetchDevelopabilityJobs } from '@/api/developability'
import { fetchDockingJobs } from '@/api/docking'
import { fetchSynthesisJobs } from '@/api/synthesis'
import { fetchMaturationJobs } from '@/api/maturation'
import { fetchMdJobs } from '@/api/md'
import type {
  DesignJob,
  DevelopabilityJob,
  DockingJob,
  MaturationJob,
  MdJob,
  SynthesisJob,
} from '@/api/types'

export type ModuleJobKind =
  | 'md'
  | 'docking'
  | 'developability'
  | 'maturation'
  | 'synthesis'
  | 'design'

export type ModuleNavItem = {
  id: string
  name: string
  status: string
  created_at: string
  kindLabel: string
}

function toNavItems(
  jobs: Array<{ id: string; name?: string | null; status: string; created_at: string }>,
  kindLabel: string,
): ModuleNavItem[] {
  return [...jobs]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .map((j) => ({
      id: j.id,
      name: j.name || j.id.slice(0, 8),
      status: j.status,
      created_at: j.created_at,
      kindLabel,
    }))
}

export const useModuleJobsStore = defineStore('moduleJobs', () => {
  const mdJobs = ref<MdJob[]>([])
  const dockingJobs = ref<DockingJob[]>([])
  const developabilityJobs = ref<DevelopabilityJob[]>([])
  const maturationJobs = ref<MaturationJob[]>([])
  const synthesisJobs = ref<SynthesisJob[]>([])
  const designJobs = ref<DesignJob[]>([])
  const loading = ref(false)

  const counts = computed(() => ({
    md: mdJobs.value.length,
    docking: dockingJobs.value.length,
    developability: developabilityJobs.value.length,
    maturation: maturationJobs.value.length,
    synthesis: synthesisJobs.value.length,
    design: designJobs.value.length,
  }))

  function recent(kind: ModuleJobKind, limit = 5): ModuleNavItem[] {
    const map: Record<ModuleJobKind, ModuleNavItem[]> = {
      md: toNavItems(mdJobs.value, 'MD'),
      docking: toNavItems(dockingJobs.value, '对接'),
      developability: toNavItems(developabilityJobs.value, '改造'),
      maturation: toNavItems(maturationJobs.value, '成熟'),
      synthesis: toNavItems(synthesisJobs.value, '合成'),
      design: toNavItems(designJobs.value, '设计'),
    }
    return map[kind].slice(0, limit)
  }

  async function refreshMd() {
    const data = await fetchMdJobs(50)
    mdJobs.value = data.items ?? []
  }

  async function refreshDocking() {
    const data = await fetchDockingJobs(50)
    dockingJobs.value = data.items ?? []
  }

  async function refreshDevelopability() {
    const data = await fetchDevelopabilityJobs(50)
    developabilityJobs.value = data.items ?? []
  }

  async function refreshMaturation() {
    const data = await fetchMaturationJobs(50)
    maturationJobs.value = data.items ?? []
  }

  async function refreshSynthesis() {
    const data = await fetchSynthesisJobs(50)
    synthesisJobs.value = data.items ?? []
  }

  async function refreshDesign() {
    const data = await fetchDesignJobs(50)
    designJobs.value = data.items ?? []
  }

  async function refreshAll() {
    loading.value = true
    try {
      await Promise.all([
        refreshMd().catch(() => undefined),
        refreshDocking().catch(() => undefined),
        refreshDevelopability().catch(() => undefined),
        refreshMaturation().catch(() => undefined),
        refreshSynthesis().catch(() => undefined),
        refreshDesign().catch(() => undefined),
      ])
    } finally {
      loading.value = false
    }
  }

  async function refresh(kind: ModuleJobKind) {
    if (kind === 'md') return refreshMd()
    if (kind === 'docking') return refreshDocking()
    if (kind === 'developability') return refreshDevelopability()
    if (kind === 'maturation') return refreshMaturation()
    if (kind === 'design') return refreshDesign()
    return refreshSynthesis()
  }

  return {
    mdJobs,
    dockingJobs,
    developabilityJobs,
    maturationJobs,
    synthesisJobs,
    designJobs,
    loading,
    counts,
    recent,
    refresh,
    refreshAll,
    refreshMd,
    refreshDocking,
    refreshDevelopability,
    refreshMaturation,
    refreshSynthesis,
    refreshDesign,
  }
})
