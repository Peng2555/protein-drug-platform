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

export interface RasDockingJob extends Job {}

export interface RasDockingJobListOut {
  items: RasDockingJob[]
  total: number
}

export interface DockingJob extends Job {}

export interface DockingJobListOut {
  items: DockingJob[]
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

export interface MaturationLogSection {
  id: string
  title: string
  content: string
  truncated: boolean
}

export interface MaturationLogsOut {
  stage: string | null
  status: string
  summary_lines: string[]
  progress: {
    num_samples?: number
    gpu_count?: number
    steps?: number
    mask_position_count?: number
    inference_total?: number
    completion_percent?: number
    maturation_fastas?: number
  }
  sections: MaturationLogSection[]
}

export interface SynthesisSelectOut {
  job_id?: string | null
  parent_cdr3?: string | null
  parent_v_gene?: string | null
  cdr3_region?: string | null
  shm_filtered: number
  matched_count: number
  matched_cdr3_kinds: number
  unmatched_iggm_count: number
  order_count: number
  a_count: number
  b_count: number
  matched_csv: string
  unmatched_csv: string
  order_csv: string
  order_txt: string
  out_dir: string
}

export interface SynthesisCandidate {
  synthesis_id: string | null
  priority: string | null
  recommend: string | null
  iggm_variant_id: string | null
  iggm_cdr3: string | null
  seq_count: number | null
  shm_row: number | null
  cdr3_mutation_sites: string | null
  extra_mutation_sites: string | null
  all_mutation_sites_for_synthesis: string | null
  n_total_mutations: number | null
  synthesis_sequence: string | null
  nucleotide_sequence: string | null
  v_gene: string | null
  j_gene: string | null
  PI: string | null
  note: string | null
  has_extra_shm?: string | null
  cdr3_mutation_sites_in_shm_row?: string | null
  extra_mutation_sites_in_shm_row?: string | null
  aa_sequence?: string | null
  iggm_frequency?: number | null
  iggm_cdr3_mutations?: string | null
  extra: Record<string, unknown>
}

export interface SynthesisCandidatesOut {
  items: SynthesisCandidate[]
  total: number
  columns: string[]
  summary: Record<string, unknown> | null
}

export interface SynthesisJob extends Job {}

export interface SynthesisJobListOut {
  items: SynthesisJob[]
  total: number
}

export interface DevelopabilityJob extends Job {
  fasta_text?: string | null
}

export interface DevelopabilityJobListOut {
  items: DevelopabilityJob[]
  total: number
}

export interface DesignJob extends Job {}

export interface DesignJobListOut {
  items: DesignJob[]
  total: number
}

export interface RosettaEvalJob extends Job {}

export interface RosettaEvalJobListOut {
  items: RosettaEvalJob[]
  total: number
}

export interface RosettaEvalRow {
  rank?: number
  name: string
  is_wt?: boolean
  dG_separated?: number | null
  ddG?: number | null
  delta_E?: number | null
  dSASA_int?: number | null
  hbonds_int?: number | null
  sc_value?: number | null
  packstat?: number | null
  final_score?: number | null
  flags?: string
}

export interface AffinityRedesignJob extends Job {}

export interface AffinityRedesignJobListOut {
  items: AffinityRedesignJob[]
  total: number
}

export interface AffinityRedesignRankedRow {
  rank?: string | number
  decision?: string
  wetlab?: string
  reason?: string
  tier?: string
  chain?: string
  label?: string
  position?: string | number
  wt?: string
  mut?: string
  region?: string
  delta_iptm?: string | number | null
  ddG?: string | number | null
  iptm?: string | number | null
  variant_id?: string
  error?: string
}

export interface AffinityRedesignRankedOut {
  ranked: AffinityRedesignRankedRow[]
  wetlab: AffinityRedesignRankedRow[]
  summary: Record<string, unknown> | null
}

export interface AffinityRedesignHit {
  chain: string
  position: number
  wt: string
  mut: string
  region: string
  label: string
  score: number | null
}

export interface AffinityRedesignProgressOut {
  stage?: string | null
  status: string
  summary_lines: string[]
  progress: Record<string, unknown>
  sections: MaturationLogSection[]
  workflow_status?: Record<string, unknown> | null
  plm_hits?: AffinityRedesignHit[]
  structure_hits?: AffinityRedesignHit[]
}

export interface MaskingPeptideJob extends Job {}

export interface MaskingPeptideJobListOut {
  items: MaskingPeptideJob[]
  total: number
}

export interface MaskingPeptideSequenceRow {
  backbone?: string
  peptide_seq?: string
  mpnn_score?: string | number | null
  length?: string | number | null
  [key: string]: unknown
}

export interface MaskingPeptideSequencesOut {
  sequences: MaskingPeptideSequenceRow[]
  summary: Record<string, unknown> | null
}

export interface DesignCandidate {
  index: number
  header?: string
  sequence: string
  chain_sequences?: string[]
  score?: number | null
  global_score?: number | null
  seq_recovery?: number | null
  temperature?: number | null
  sample?: number | null
  is_native?: boolean
}

export interface DevelopabilityAaScore {
  aa: string
  ll: number
  dll: number
  is_wt: boolean
  maxwell_ddg?: number | null
}

export interface DevelopabilityResidue {
  index: number
  aa: string
  kabat: string
  region: string
  tier: 'freeze' | 'candidate' | 'avoid'
  freeze_reason: string | null
  wt_ll: number | null
  best_aa: string | null
  best_dll: number | null
  best_maxwell_aa?: string | null
  best_maxwell_ddg?: number | null
  aa_scores: DevelopabilityAaScore[]
}

export interface DevelopabilityCandidate {
  rank: number
  parent_id: string
  chain: string
  seq_pos: number
  kabat: string
  wt: string
  mut: string
  mutation: string
  region: string
  buried: boolean | null
  interface: boolean
  esm_dll: number
  hydro_delta: number
  maxwell_ddg?: number | null
  pass_esm: boolean
  pass_hydro: boolean
  pass_tm: boolean | null
  status: string
}

