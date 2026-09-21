import { api, apiJson } from './client'
import { downloadBlob } from '@/utils/download'

export interface AntibodyProject {
  id: string
  owner_id: string
  project_code: string
  name: string
  target_name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface ProjectMember {
  id: string
  user_id: string
  username: string
  role: 'owner' | 'editor' | 'viewer'
  created_at: string
}

export interface CdrSpan {
  name: string
  start: number
  end: number
  kabat_range?: string
  sequence?: string
}

export interface ChainAnnotation {
  domain?: string
  scheme?: string
  numbered_length?: number
  cdr_spans?: CdrSpan[]
  kabat_labels?: string[]
}

export interface VersionChain {
  id: string
  chain_role: string
  chain_name: string | null
  variable_sequence: string
  full_sequence: string | null
  nucleotide_sequence: string | null
  sequence_hash: string
  numbering_scheme: string
  annotation_json: ChainAnnotation | Record<string, unknown> | null
  annotation_tool: string | null
  annotation_version: string | null
}

export interface VersionMutation {
  id: string
  chain_role: string
  mutation_type: string
  sequence_position: number | null
  numbering_label: string | null
  kabat_label: string | null
  from_aa: string | null
  to_aa: string | null
  region: string | null
  rationale: string | null
  expected_effect: string | null
  evidence: string | null
}

export interface AntibodyVersion {
  id: string
  candidate_id: string
  primary_parent_id: string | null
  version_code: string
  version_number: number
  name: string | null
  status: 'draft' | 'locked' | 'tested' | 'rejected'
  purpose: string | null
  rationale: string | null
  evidence: string | null
  sequence_hash: string
  created_by: string
  created_at: string
  updated_at: string
  locked_at: string | null
  chains: VersionChain[]
  mutations: VersionMutation[]
}

export interface AntibodyCandidate {
  id: string
  project_id: string
  candidate_code: string
  name: string
  antibody_category: 'RM' | 'RN' | 'RL' | null
  antibody_type: 'igg' | 'vhh'
  description: string | null
  status: string
  created_by: string
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface SampleBatch {
  id: string
  version_id: string
  batch_code: string
  expression_date: string | null
  purification_date: string | null
  concentration_value: number | null
  concentration_unit: string | null
  purity_percent: number | null
  storage_location: string | null
  operator_id: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface Measurement {
  id: string
  metric_name: string
  value_numeric: number | null
  value_text: string | null
  unit: string | null
  qualifier: string | null
  replicate: number | null
  notes: string | null
  created_at: string
}

export interface AffinityPreviewRow {
  excel_row: number
  loading_sample_id: string
  protein_key: string
  antigen: string
  loading_response: number | null
  response: number | null
  kd_m: number | null
  kd_qualifier: string | null
  ka: number | null
  ka_qualifier: string | null
  kdis: number | null
  kdis_qualifier: string | null
  result: string | null
  status: string
  version_id: string | null
  version_code: string | null
  version_name: string | null
  selected: boolean
  message: string | null
}

export interface AffinityPreview {
  sheet_name: string
  rows: AffinityPreviewRow[]
  matched: number
  unmatched: number
  control: number
  duplicate: number
}

export interface Experiment {
  id: string
  project_id: string
  version_id: string
  sample_batch_id: string | null
  title: string
  experiment_type: string
  experiment_date: string | null
  operator_id: string | null
  conditions_json: Record<string, unknown> | null
  result_summary: string | null
  notes: string | null
  created_at: string
  updated_at: string
  measurements: Measurement[]
}

export interface VersionComparison {
  base_version: AntibodyVersion
  target_version: AntibodyVersion
  differences: Array<{
    chain_role: string
    mutation_type: string
    sequence_position: number | null
    from_aa: string | null
    to_aa: string | null
  }>
}

export interface ProjectArtifact {
  id: string
  project_id: string
  version_id: string | null
  sample_batch_id: string | null
  experiment_id: string | null
  job_link_id: string | null
  category: string
  file_name: string
  sha256: string
  size_bytes: number
  mime_type: string | null
  created_at: string
}

export interface ProjectJobLink {
  id: string
  project_id: string
  version_id: string
  job_id: string | null
  original_job_id: string
  engine: string
  purpose: string | null
  input_sequence_hash: string
  params_snapshot: Record<string, unknown> | null
  result_snapshot: Record<string, unknown> | null
  linked_by: string
  created_at: string
}

export interface AuditEvent {
  id: string
  project_id: string
  entity_type: string
  entity_id: string
  action: string
  actor_id: string | null
  before_json: Record<string, unknown> | null
  after_json: Record<string, unknown> | null
  request_id: string | null
  created_at: string
}

export interface ChainInput {
  chain_role: string
  variable_sequence: string
  full_sequence?: string | null
  chain_name?: string | null
}

const root = '/api/antibody-projects'

export const fetchAntibodyProjects = (includeArchived = false) =>
  apiJson<AntibodyProject[]>(`${root}?include_archived=${includeArchived}`)
export const fetchAntibodyProject = (id: string) => apiJson<AntibodyProject>(`${root}/${id}`)
export const createAntibodyProject = (data: {
  project_code: string
  name: string
  target_name: string
  description?: string
}) => apiJson<AntibodyProject>(root, { method: 'POST', data })
export const updateAntibodyProject = (id: string, data: Partial<AntibodyProject>) =>
  apiJson<AntibodyProject>(`${root}/${id}`, { method: 'PATCH', data })

export const fetchProjectMembers = (projectId: string) =>
  apiJson<ProjectMember[]>(`${root}/${projectId}/members`)
export const addProjectMember = (projectId: string, data: { username: string; role: string }) =>
  apiJson<ProjectMember>(`${root}/${projectId}/members`, { method: 'POST', data })

export const fetchCandidates = (projectId: string) =>
  apiJson<AntibodyCandidate[]>(`${root}/${projectId}/candidates`)
export const createCandidate = (
  projectId: string,
  data: {
    candidate_code: string
    name: string
    antibody_category: 'RM' | 'RN' | 'RL'
    antibody_type: 'igg' | 'vhh'
    description?: string
    chains: ChainInput[]
  },
) => apiJson<AntibodyCandidate>(`${root}/${projectId}/candidates`, { method: 'POST', data })
export const setCandidateCategory = (
  projectId: string,
  candidateId: string,
  antibodyCategory: 'RM' | 'RN' | 'RL',
) => apiJson<AntibodyCandidate>(
  `${root}/${projectId}/candidates/${candidateId}/category`,
  { method: 'PATCH', data: { antibody_category: antibodyCategory } },
)

export const fetchVersions = (projectId: string, candidateId: string) =>
  apiJson<AntibodyVersion[]>(`${root}/${projectId}/candidates/${candidateId}/versions`)
export const createVersion = (
  projectId: string,
  candidateId: string,
  data: {
    parent_version_id: string
    name?: string
    chains: ChainInput[]
  },
) => apiJson<AntibodyVersion>(
  `${root}/${projectId}/candidates/${candidateId}/versions`,
  { method: 'POST', data },
)
export const importVersions = (
  projectId: string,
  candidateId: string,
  data: {
    parent_version_id: string
    items: Array<{ name?: string; chains: ChainInput[] }>
  },
) => apiJson<AntibodyVersion[]>(
  `${root}/${projectId}/candidates/${candidateId}/versions/import`,
  { method: 'POST', data },
)
export const importVersionsFromFasta = (
  projectId: string,
  candidateId: string,
  parentVersionId: string,
  file: File,
) => {
  const form = new FormData()
  form.append('parent_version_id', parentVersionId)
  form.append('file', file)
  return apiJson<AntibodyVersion[]>(
    `${root}/${projectId}/candidates/${candidateId}/versions/import-fasta`,
    { method: 'POST', data: form },
  )
}
export const importVersionsFromXlsx = (
  projectId: string,
  candidateId: string,
  parentVersionId: string,
  file: File,
) => {
  const form = new FormData()
  form.append('parent_version_id', parentVersionId)
  form.append('file', file)
  return apiJson<AntibodyVersion[]>(
    `${root}/${projectId}/candidates/${candidateId}/versions/import-xlsx`,
    { method: 'POST', data: form },
  )
}
export const lockVersion = (projectId: string, versionId: string) =>
  apiJson<AntibodyVersion>(`${root}/${projectId}/versions/${versionId}/lock`, { method: 'POST' })
export const lockDraftVersions = (
  projectId: string,
  candidateId: string,
  roundCode?: string,
) => apiJson<AntibodyVersion[]>(
  `${root}/${projectId}/candidates/${candidateId}/versions/lock-drafts`,
  { method: 'POST', data: { round: roundCode || null } },
)
export const updateMutation = (
  projectId: string,
  versionId: string,
  mutationId: string,
  data: { rationale?: string; expected_effect?: string; evidence?: string },
) => apiJson<AntibodyVersion>(
  `${root}/${projectId}/versions/${versionId}/mutations/${mutationId}`,
  { method: 'PATCH', data },
)
export const compareVersions = (projectId: string, baseId: string, targetId: string) =>
  apiJson<VersionComparison>(
    `${root}/${projectId}/compare?base_version_id=${encodeURIComponent(baseId)}`
      + `&target_version_id=${encodeURIComponent(targetId)}`,
  )

export const fetchSamples = (projectId: string) =>
  apiJson<SampleBatch[]>(`${root}/${projectId}/samples`)
export const createSample = (projectId: string, data: Record<string, unknown>) =>
  apiJson<SampleBatch>(`${root}/${projectId}/samples`, { method: 'POST', data })
export const fetchExperiments = (projectId: string) =>
  apiJson<Experiment[]>(`${root}/${projectId}/experiments`)
export const createExperiment = (projectId: string, data: Record<string, unknown>) =>
  apiJson<Experiment>(`${root}/${projectId}/experiments`, { method: 'POST', data })
export const previewAffinityXlsx = (
  projectId: string,
  candidateId: string,
  file: File,
) => {
  const form = new FormData()
  form.append('file', file)
  return apiJson<AffinityPreview>(
    `${root}/${projectId}/candidates/${candidateId}/experiments/preview-affinity-xlsx`,
    { method: 'POST', data: form },
  )
}
export const importAffinityXlsx = (
  projectId: string,
  candidateId: string,
  items: AffinityPreviewRow[],
) => apiJson<Experiment[]>(
  `${root}/${projectId}/candidates/${candidateId}/experiments/import-affinity-xlsx`,
  {
    method: 'POST',
    data: {
      items: items.map((item) => ({
        excel_row: item.excel_row,
        version_id: item.version_id as string,
        loading_sample_id: item.loading_sample_id,
        protein_key: item.protein_key,
        antigen: item.antigen,
        loading_response: item.loading_response,
        response: item.response,
        kd_m: item.kd_m,
        kd_qualifier: item.kd_qualifier,
        ka: item.ka,
        ka_qualifier: item.ka_qualifier,
        kdis: item.kdis,
        kdis_qualifier: item.kdis_qualifier,
        result: item.result,
      })),
    },
  },
)

export const fetchJobLinks = (projectId: string) =>
  apiJson<ProjectJobLink[]>(`${root}/${projectId}/job-links`)
export const createJobLink = (projectId: string, data: {
  version_id: string
  job_id: string
  purpose?: string
}) => apiJson<ProjectJobLink>(`${root}/${projectId}/job-links`, { method: 'POST', data })

export const fetchArtifacts = (projectId: string) =>
  apiJson<ProjectArtifact[]>(`${root}/${projectId}/artifacts`)
export async function uploadArtifact(projectId: string, form: FormData) {
  return apiJson<ProjectArtifact>(`${root}/${projectId}/artifacts`, { method: 'POST', data: form })
}
export async function downloadArtifact(projectId: string, artifact: ProjectArtifact) {
  const response = await api.get<Blob>(
    `${root}/${projectId}/artifacts/${artifact.id}/download`,
    { responseType: 'blob' },
  )
  downloadBlob(response.data, artifact.file_name)
}

export const fetchAuditEvents = (projectId: string) =>
  apiJson<AuditEvent[]>(`${root}/${projectId}/audit-events`)
