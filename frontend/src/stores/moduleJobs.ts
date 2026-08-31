import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchDesignJobs } from '@/api/design'
import { fetchRosettaEvalJobs } from '@/api/rosetta'
import { fetchDevelopabilityJobs } from '@/api/developability'
import { fetchDockingJobs } from '@/api/docking'
import { fetchSynthesisJobs } from '@/api/synthesis'
import { fetchMaturationJobs } from '@/api/maturation'
import { fetchAffinityRedesignJobs } from '@/api/affinityRedesign'
import { fetchMaskingPeptideJobs } from '@/api/maskingPeptide'
import { fetchMdJobs } from '@/api/md'
import type {
  AffinityRedesignJob,
  DesignJob,
  DevelopabilityJob,
  DockingJob,
  MaskingPeptideJob,
  MaturationJob,
  MdJob,
  RosettaEvalJob,
  SynthesisJob,
} from '@/api/types'

export type ModuleJobKind =
  | 'md'
  | 'docking'
  | 'developability'
  | 'maturation'
  | 'affinity_redesign'
  | 'masking_peptide'
  | 'synthesis'
  | 'design'
  | 'rosetta'

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
  const affinityRedesignJobs = ref<AffinityRedesignJob[]>([])
  const maskingPeptideJobs = ref<MaskingPeptideJob[]>([])
  const synthesisJobs = ref<SynthesisJob[]>([])
  const designJobs = ref<DesignJob[]>([])
  const rosettaJobs = ref<RosettaEvalJob[]>([])
  const loading = ref(false)

  const counts = computed(() => ({
    md: mdJobs.value.length,
    docking: dockingJobs.value.length,
    developability: developabilityJobs.value.length,
    maturation: maturationJobs.value.length,
    affinity_redesign: affinityRedesignJobs.value.length,
    masking_peptide: maskingPeptideJobs.value.length,
    synthesis: synthesisJobs.value.length,
    design: designJobs.value.length,
    rosetta: rosettaJobs.value.length,
  }))

  function recent(kind: ModuleJobKind, limit = 5): ModuleNavItem[] {
    const map: Record<ModuleJobKind, ModuleNavItem[]> = {
      md: toNavItems(mdJobs.value, 'MD'),
      docking: toNavItems(dockingJobs.value, '对接'),
      developability: toNavItems(developabilityJobs.value, '改造'),
      maturation: toNavItems(maturationJobs.value, '成熟'),
      affinity_redesign: toNavItems(affinityRedesignJobs.value, '改造'),
      masking_peptide: toNavItems(maskingPeptideJobs.value, '多肽'),
      synthesis: toNavItems(synthesisJobs.value, '合成'),
      design: toNavItems(designJobs.value, '设计'),
      rosetta: toNavItems(rosettaJobs.value, '评价'),
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

  async function refreshAffinityRedesign() {
    const data = await fetchAffinityRedesignJobs(50)
    affinityRedesignJobs.value = data.items ?? []
  }

  async function refreshMaskingPeptide() {
    const data = await fetchMaskingPeptideJobs(50)
    maskingPeptideJobs.value = data.items ?? []
  }

  async function refreshSynthesis() {
    const data = await fetchSynthesisJobs(50)
    synthesisJobs.value = data.items ?? []
  }

  async function refreshDesign() {
    const data = await fetchDesignJobs(50)
    designJobs.value = data.items ?? []
  }

  async function refreshRosetta() {
    const data = await fetchRosettaEvalJobs(50)
    rosettaJobs.value = data.items ?? []
  }

  async function refreshAll() {
    loading.value = true
    try {
      await Promise.all([
        refreshMd().catch(() => undefined),
        refreshDocking().catch(() => undefined),
        refreshDevelopability().catch(() => undefined),
        refreshMaturation().catch(() => undefined),
        refreshAffinityRedesign().catch(() => undefined),
        refreshMaskingPeptide().catch(() => undefined),
        refreshSynthesis().catch(() => undefined),
        refreshDesign().catch(() => undefined),
        refreshRosetta().catch(() => undefined),
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
    if (kind === 'affinity_redesign') return refreshAffinityRedesign()
    if (kind === 'masking_peptide') return refreshMaskingPeptide()
    if (kind === 'design') return refreshDesign()
    if (kind === 'rosetta') return refreshRosetta()
    return refreshSynthesis()
  }

  return {
    mdJobs,
    dockingJobs,
    developabilityJobs,
    maturationJobs,
    affinityRedesignJobs,
    maskingPeptideJobs,
    synthesisJobs,
    designJobs,
    rosettaJobs,
    loading,
    counts,
    recent,
    refresh,
    refreshAll,
    refreshMd,
    refreshDocking,
    refreshDevelopability,
    refreshMaturation,
    refreshAffinityRedesign,
    refreshMaskingPeptide,
    refreshSynthesis,
    refreshDesign,
    refreshRosetta,
  }
})
