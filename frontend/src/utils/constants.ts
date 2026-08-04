export const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  done: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export const BATCH_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '进行中',
  done: '已完成',
  partial: '部分完成',
  failed: '失败',
  cancelled: '已取消',
}

export const MD_STAGE_LABELS: Record<string, string> = {
  queued: '排队',
  prep: '结构准备',
  topo: '拓扑构建',
  equil: '平衡',
  prod: '生产模拟',
  analysis: '分析',
  done: '完成',
}

export const BATCH_JOBS_PAGE_SIZE = 100

export const EXAMPLE_FASTA = `>H
DVQLVESGGGSVQAGGSLRLSCAASGYIASINYLGWFRQAPGKEREGVAAVSPAGGTPYYADSVKGRFTVSLDNAENTVYLQMNSLKPEDTALYYCAAARQGWYIPLNSYGYNYWGQGTQVTVSSRGRHHHHHH
>A
KVFGRCELAAAMKRHGLDNYRGYSLGNWVCAAKFESNFNTQATNRNTDGSTDYGILQINSRWWCNDGRTPGSRNLCNIPCSALLSSDITASVNCAKKIVSDGNGMNAWVAWRNRCKGTDVQAWIRGCRL`

export function statusLabel(status: string) {
  return STATUS_LABELS[status] || status
}

export function batchStatusLabel(status: string) {
  return BATCH_STATUS_LABELS[status] || status
}

export function engineLabel(engine?: string) {
  if (engine === 'esmfold2') return 'ESMFold2'
  if (engine === 'boltz2') return 'Boltz2'
  return engine || '—'
}

export function formatEsmfoldParams(params?: Record<string, number>) {
  if (!params) return ''
  return `loops=${params.num_loops} · steps=${params.num_sampling_steps} · samples=${params.num_diffusion_samples}`
}
