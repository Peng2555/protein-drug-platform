/** API types aligned with backend Pydantic schemas. */

export interface Job {
  id: string
  name: string | null
  batch_id: string | null
  heavy_chain_id: string | null
  parent_job_id: string | null
  engine: string
  status: string
  stage: string | null
  chains_json: Record<string, number>
  total_length: number
  use_msa_server: boolean
  params_json: Record<string, unknown> | null
  results_json: Record<string, unknown> | null
  iptm: number | null
  ptm: number | null
  confidence_score: number | null
  complex_plddt: number | null
  dockq: number | null
  pdockq: number | null
  pdockq2: number | null
  runtime_seconds: number | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface JobListOut {
  items: Job[]
  total: number
}

export interface Batch {
  id: string
  name: string
  batch_type: string
  target_name: string
  target_chain_id: string
  heavy_chain_id: string
  heavy_chain_count: number
  use_msa_server: boolean
  created_at: string
  status: string
  done_count: number
  running_count: number
  queued_count: number
  failed_count: number
  cancelled_count: number
}

export interface BatchDetail extends Batch {
  target_sequence: string
}

export interface BatchListOut {
  items: Batch[]
  total: number
}

export interface BatchJobsListOut {
  items: Job[]
  total: number
  limit: number
  offset: number
}

export interface VhhPanelCreateOut {
  batch: Batch
  job_ids: string[]
  skipped_duplicates: number
}

export interface CdrSpan {
  name: string
  start: number
  end: number
  kabat_range: string
  sequence: string
}

export interface Residue {
  index: number
  aa: string
  kabat: string
}

export interface ChainSequence {
  chain_id: string
  length: number
  sequence: string
  is_antibody: boolean
  domain: string | null
  scheme: string | null
  cdr_spans: CdrSpan[]
  residues: Residue[]
}

export interface JobSequencesOut {
  job_id: string
  chains: ChainSequence[]
}

export interface MdJob extends Job {}

export interface MdJobListOut {
  items: MdJob[]
  total: number
}

export interface MaturationJob extends Job {}

export interface MaturationJobListOut {
  items: MaturationJob[]
  total: number
}

export interface MaturationVariant {
  method: string | null
  antibody_seq_h: string | null
  frequency: number | null
  diff: string | null
  mutations: string | null
  extra: Record<string, unknown>
}

export interface MaturationVariantsOut {
  items: MaturationVariant[]
  total: number
  columns: string[]
}
