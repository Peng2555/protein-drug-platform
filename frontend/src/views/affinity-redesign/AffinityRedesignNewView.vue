<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  CircleCheck,
  Document,
  UploadFilled,
} from '@element-plus/icons-vue'
import { createAffinityRedesignJob, uploadAffinityRedesignJob } from '@/api/affinityRedesign'
import BoltzChainBuilder, {
  type ChainEntity,
} from '@/components/fold/BoltzChainBuilder.vue'
import { EXAMPLE_FASTA } from '@/utils/constants'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const moduleJobs = useModuleJobsStore()

function newEntity(partial?: Partial<ChainEntity>): ChainEntity {
  return {
    key: `c_${Math.random().toString(36).slice(2, 9)}`,
    entity: 'protein',
    copies: 1,
    ids: ['H'],
    sequence: '',
    ligandMode: 'smiles',
    smiles: '',
    ccd: '',
    cyclic: false,
    modifications: [],
    plainView: false,
    ...partial,
  }
}

const chainEntities = ref<ChainEntity[]>([
  newEntity({ ids: ['H'], key: 'c_h' }),
  newEntity({ ids: ['A'], key: 'c_a' }),
])

const name = ref('')
const complexFile = ref<File | null>(null)
const skipRound1 = ref(false)
const showAdvanced = ref(false)
const submitting = ref(false)
const entryMode = ref<'with_structure' | 'sequence_only'>('sequence_only')

const pipelineSteps = [
  { id: 'round1', label: 'Round1 双轨', desc: 'PLM + 结构轨采样' },
  { id: 'boltz2', label: 'Boltz2 全量', desc: 'WT + 候选折叠' },
  { id: 'rosetta', label: 'Rosetta', desc: '界面 ΔΔG 排序' },
  { id: 'export', label: '导出', desc: 'ranked / wetlab' },
]

const entryHint = computed(() =>
  entryMode.value === 'with_structure'
    ? '入口 A：上传已有抗体–抗原复合物 PDB/CIF，跳过 WT 折结构步骤。'
    : '入口 B：仅提供序列，流水线将先用 Boltz2 预测 WT 复合物，再进入 round1。',
)

function onComplexUpload(arg: { raw?: File }) {
  complexFile.value = arg.raw || null
}

function clearComplex() {
  complexFile.value = null
}

function setEntry(mode: 'with_structure' | 'sequence_only') {
  entryMode.value = mode
  if (mode === 'sequence_only') complexFile.value = null
}

function parseFastaToEntities(fasta: string): ChainEntity[] {
  const blocks: Array<{ id: string; seq: string }> = []
  let id: string | null = null
  let parts: string[] = []
  for (const raw of fasta.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('>')) {
      if (id != null) blocks.push({ id, seq: parts.join('') })
      id = line.slice(1).split(/\s+/)[0] || 'H'
      parts = []
    } else {
      parts.push(line.replace(/\s/g, ''))
    }
  }
  if (id != null) blocks.push({ id, seq: parts.join('') })
  if (!blocks.length) return [newEntity({ ids: ['H'] }), newEntity({ ids: ['A'] })]
  return blocks.map((b, i) =>
    newEntity({
      key: `ex_${i}`,
      ids: [b.id.slice(0, 4)],
      sequence: b.seq,
    }),
  )
}

function entitiesToFasta(entities: ChainEntity[]): string {
  const lines: string[] = []
  for (const e of entities) {
    if (e.entity !== 'protein') continue
    const seq = e.sequence.replace(/\s/g, '')
    if (!seq) continue
    for (const id of e.ids) {
      lines.push(`>${id}`)
      lines.push(seq)
    }
  }
  return lines.join('\n')
}

function validateChains(): string | null {
  if (!chainEntities.value.length) return '请至少添加一条链'
  const ids: string[] = []
  for (const e of chainEntities.value) {
    if (e.entity !== 'protein') return '亲和力改造仅支持蛋白链'
    const seq = e.sequence.replace(/\s/g, '')
    if (!seq) return `请填写链 ${e.ids[0] || '?'} 的序列`
    if (seq.length < 10) return `链 ${e.ids[0]} 序列过短`
    for (const id of e.ids) {
      if (ids.includes(id)) return `链 ID「${id}」重复，请修改为 H / L / A 等不同 ID`
      ids.push(id)
    }
  }
  if (!ids.includes('A') && !ids.some((id) => !['H', 'L'].includes(id))) {
    return '建议包含抗原链 A（或指定其他非 H/L 链作为抗原）'
  }
  return null
}

async function submit() {
  const err = validateChains()
  if (err) {
    ElMessage.warning(err)
    return
  }
  const fasta = entitiesToFasta(chainEntities.value)
  if (entryMode.value === 'with_structure' && !complexFile.value) {
    ElMessage.warning('入口 A 请上传复合物结构，或切换到「仅序列」')
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: name.value.trim() || null,
      skip_round1: skipRound1.value,
    }
    const job =
      entryMode.value === 'with_structure' && complexFile.value
        ? await uploadAffinityRedesignJob(fasta, complexFile.value, payload)
        : await createAffinityRedesignJob({ ...payload, fasta })
    await moduleJobs.refreshAffinityRedesign()
    ElMessage.success('任务已提交，将进入 round1 → Boltz2 → Rosetta 流水线')
    router.push({ name: 'affinity-redesign-task', params: { id: job.id } })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

function fillExample() {
  chainEntities.value = parseFastaToEntities(EXAMPLE_FASTA)
  name.value = 'vhh_lysozyme_demo'
}
</script>

<template>
  <div class="ar-form">
    <button type="button" class="ar-form__back" @click="router.push({ name: 'workflows' })">
      <el-icon><ArrowLeft /></el-icon>
      返回工作流
    </button>

    <header class="ar-form__hero">
      <div class="ar-form__hero-top">
        <h1>亲和力改造</h1>
        <span class="ar-form__badge">端到端流水线</span>
        <span class="ar-form__meta">~2–6 h</span>
      </div>
      <p class="ar-form__desc">
        round1 双轨采样 → Boltz2 全量折叠 → Rosetta 界面评价 → 导出 ranked / wetlab 短名单。长任务走
        Celery 异步，Boltz2 与 fold 共用 GPU。
      </p>
    </header>

    <div class="ar-form__pipeline" aria-label="流水线步骤">
      <div v-for="(step, i) in pipelineSteps" :key="step.id" class="ar-form__pipe-item">
        <span class="ar-form__pipe-num">{{ i + 1 }}</span>
        <div>
          <strong>{{ step.label }}</strong>
          <span>{{ step.desc }}</span>
        </div>
        <el-icon v-if="i < pipelineSteps.length - 1" class="ar-form__pipe-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <div class="ar-form__layout">
      <div class="ar-form__main">
        <section class="ar-section">
          <h2 class="ar-section__title">入口方式</h2>
          <div class="ar-form__tabs">
            <button
              type="button"
              class="ar-form__tab"
              :class="{ active: entryMode === 'sequence_only' }"
              @click="setEntry('sequence_only')"
            >
              入口 B · 仅序列
            </button>
            <button
              type="button"
              class="ar-form__tab"
              :class="{ active: entryMode === 'with_structure' }"
              @click="setEntry('with_structure')"
            >
              入口 A · 已有复合物
            </button>
          </div>
          <p class="field__hint">{{ entryHint }}</p>
        </section>

        <section class="ar-section">
          <div class="field">
            <label class="field__label">任务名称</label>
            <p class="field__hint">可选。便于在任务列表中检索；留空则自动生成。</p>
            <el-input v-model="name" placeholder="例如 lycov1404 VHH" maxlength="128" size="large" />
          </div>

          <div class="field">
            <div class="field__row">
              <label class="field__label">序列 / 分子 <span class="req">*</span></label>
              <button type="button" class="link-btn" @click="fillExample">加载示例</button>
            </div>
            <p class="field__hint">
              默认 VHH + 抗原（链 H、A）；IgG 可 <strong>Add chain</strong> 添加轻链 L。链 ID 需与
              campaign 配置一致。
            </p>
            <BoltzChainBuilder
              v-model="chainEntities"
              chain-id-mode="antibody"
              :allow-ligand="false"
            />
          </div>

          <div v-if="entryMode === 'with_structure'" class="field">
            <label class="field__label">复合物结构 <span class="req">*</span></label>
            <p class="field__hint">PDB / CIF / mmCIF，抗体–抗原复合物坐标。</p>
            <div v-if="complexFile" class="upload-done">
              <el-icon><Document /></el-icon>
              <span>{{ complexFile.name }}</span>
              <button type="button" class="link-btn" @click="clearComplex">移除</button>
            </div>
            <el-upload
              v-else
              drag
              class="upload-zone"
              :auto-upload="false"
              :limit="1"
              :show-file-list="false"
              accept=".pdb,.cif,.mmcif"
              @change="onComplexUpload"
            >
              <el-icon class="upload-zone__icon"><UploadFilled /></el-icon>
              <p class="upload-zone__title">拖拽或点击上传复合物结构</p>
              <p class="upload-zone__sub">支持 .pdb · .cif · .mmcif</p>
            </el-upload>
          </div>
        </section>

        <section class="ar-section ar-section--muted">
          <button type="button" class="optional-toggle" @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '▾' : '▸' }} 高级选项
          </button>
          <div v-show="showAdvanced" class="advanced-box">
            <el-checkbox v-model="skipRound1">
              跳过 round1（复用 campaign 内已有 round1/merged；demo 或重跑 rescore 时使用）
            </el-checkbox>
          </div>
        </section>

        <div class="actions">
          <el-button
            type="primary"
            size="large"
            class="actions__submit"
            :loading="submitting"
            @click="submit"
          >
            提交流水线
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
          <p class="actions__warn">提交后可在任务详情页查看 stage 进度与 ranked 表。</p>
        </div>
      </div>

      <aside class="ar-form__aside">
        <div class="info-card info-card--accent">
          <h3>筛选规则</h3>
          <ul>
            <li><strong>ΔipTM &lt; −0.03</strong> → drop</li>
            <li><strong>ddG &gt; 3</strong> → review</li>
            <li>不做 top-N：过门槛的全部保留</li>
            <li>A / C 全部进 Boltz2；B（仅结构）默认软上限 100</li>
            <li>冻住 N 端 1–4（QVQL）；C 端只冻 <code>TVSS</code></li>
          </ul>
        </div>
        <div class="info-card">
          <h3>产物</h3>
          <ul>
            <li><code>ranked_mutations.csv</code> 全表</li>
            <li><code>wetlab_candidates.csv</code> 湿实验短名单</li>
            <li><code>structures/</code> WT + 短名单 PDB</li>
            <li><code>summary.json</code> 汇总指标</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>资源占用</h3>
          <p>
            <el-icon><CircleCheck /></el-icon>
            Boltz2 阶段占用 GPU（与 fold 同队列）
          </p>
          <p>
            <el-icon><CircleCheck /></el-icon>
            Rosetta 仅 CPU，可并行
          </p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped lang="scss">
.ar-form {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0.25rem 0 2.5rem;
}

.ar-form__back {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1rem;
  padding: 0.35rem 0.5rem;
  border: none;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  color: #6b7280;
  background: transparent;
  cursor: pointer;

  &:hover {
    color: #111827;
    background: #f3f4f6;
  }
}

.ar-form__hero {
  margin-bottom: 1.35rem;
}

.ar-form__hero-top {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;

  h1 {
    margin: 0;
    font-size: clamp(1.5rem, 2.8vw, 1.85rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #111827;
  }
}

.ar-form__badge {
  padding: 0.22rem 0.6rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #0f766e;
  background: linear-gradient(135deg, #ecfdf5, #f0fdfa);
  border: 1px solid #a7f3d0;
}

.ar-form__meta {
  font-size: 0.78rem;
  color: #9ca3af;
  font-weight: 600;
}

.ar-form__desc {
  margin: 0.55rem 0 0;
  max-width: 52rem;
  font-size: 0.92rem;
  line-height: 1.65;
  color: #6b7280;
}

.ar-form__pipeline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.15rem;
  margin-bottom: 1.5rem;
  padding: 0.85rem 1rem;
  border-radius: 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f0fdfa 100%);
  border: 1px solid #e2e8f0;
}

.ar-form__pipe-item {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.35rem 0.5rem 0.35rem 0.35rem;
  border-radius: 999px;
  background: #fff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);

  strong {
    display: block;
    font-size: 0.76rem;
    font-weight: 700;
    color: #111827;
    line-height: 1.2;
  }

  span {
    font-size: 0.65rem;
    color: #9ca3af;
  }
}

.ar-form__pipe-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.68rem;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green, #00aca1), var(--bio-blue, #2563eb));
}

.ar-form__pipe-arrow {
  margin: 0 0.15rem;
  color: #cbd5e1;
  font-size: 0.85rem;
}

.ar-form__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 1.5rem;
  align-items: start;
}

.ar-form__main {
  min-width: 0;
}

.ar-section {
  margin-bottom: 1.25rem;
  padding: 1.35rem 1.4rem;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);

  &--muted {
    background: #fafbfc;
    box-shadow: none;
  }
}

.ar-section__title {
  margin: 0 0 0.85rem;
  font-size: 0.88rem;
  font-weight: 700;
  color: #374151;
  letter-spacing: 0.02em;
}

.ar-form__tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.65rem;
  padding: 0.25rem;
  background: #f3f4f6;
  border-radius: 10px;
}

.ar-form__tab {
  flex: 1;
  border: none;
  background: transparent;
  color: #6b7280;
  padding: 0.62rem 0.75rem;
  border-radius: 8px;
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s;

  &.active {
    background: #fff;
    color: #111827;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
  }

  &:hover:not(.active) {
    color: #374151;
  }
}

.field {
  margin-bottom: 1.25rem;

  &:last-child {
    margin-bottom: 0;
  }
}

.field__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.field__label {
  display: block;
  font-size: 0.92rem;
  font-weight: 700;
  color: #111827;
  margin-bottom: 0.25rem;
}

.field__hint {
  margin: 0 0 0.55rem;
  font-size: 0.78rem;
  line-height: 1.55;
  color: #9ca3af;

  code {
    padding: 0.1rem 0.35rem;
    border-radius: 4px;
    font-size: 0.76rem;
    background: #f3f4f6;
    color: #374151;
  }
}

.req {
  color: #ef4444;
}

.link-btn {
  border: none;
  background: transparent;
  color: #0d9488;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

.upload-zone {
  width: 100%;

  :deep(.el-upload) {
    width: 100%;
  }

  :deep(.el-upload-dragger) {
    width: 100%;
    padding: 1.75rem 1.25rem;
    border-radius: 14px;
    border: 2px dashed #d1d5db;
    background: #fafbfc;
    transition:
      border-color 0.15s,
      background 0.15s;

    &:hover {
      border-color: var(--bio-green, #00aca1);
      background: #f0fdfa;
    }
  }
}

.upload-zone__icon {
  font-size: 2.2rem;
  color: #94a3b8;
  margin-bottom: 0.5rem;
}

.upload-zone__title {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: #374151;
}

.upload-zone__sub {
  margin: 0;
  font-size: 0.78rem;
  color: #9ca3af;
}

.upload-done {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.85rem 1rem;
  border-radius: 12px;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  font-size: 0.88rem;
  color: #065f46;

  span {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.optional-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 0.88rem;
  font-weight: 700;
  color: #111827;
  cursor: pointer;
}

.advanced-box {
  margin-top: 0.85rem;
  padding-top: 0.85rem;
  border-top: 1px solid #e5e7eb;
  font-size: 0.84rem;
  color: #4b5563;
}

.actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.5rem 0 0;
}

.actions__submit {
  min-width: 180px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.actions__arrow {
  margin-left: 0.25rem;
}

.actions__warn {
  margin: 0;
  font-size: 0.8rem;
  color: #9ca3af;
}

.ar-form__aside {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  position: sticky;
  top: 1rem;
}

.info-card {
  padding: 1.1rem 1.15rem;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #e5e7eb;

  h3 {
    margin: 0 0 0.65rem;
    font-size: 0.82rem;
    font-weight: 700;
    color: #111827;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 0.45rem;
  }

  li {
    font-size: 0.78rem;
    line-height: 1.5;
    color: #6b7280;

    strong {
      color: #374151;
    }
  }

  code {
    font-size: 0.72rem;
    padding: 0.08rem 0.3rem;
    border-radius: 4px;
    background: #f3f4f6;
    color: #374151;
  }

  p {
    display: flex;
    align-items: flex-start;
    gap: 0.4rem;
    margin: 0 0 0.4rem;
    font-size: 0.78rem;
    line-height: 1.5;
    color: #6b7280;

    &:last-child {
      margin-bottom: 0;
    }

    .el-icon {
      flex-shrink: 0;
      margin-top: 0.15rem;
      color: var(--bio-green, #00aca1);
    }
  }

  &--accent {
    border-color: #a7f3d0;
    background: linear-gradient(180deg, #f0fdfa 0%, #fff 100%);
  }
}

@media (max-width: 900px) {
  .ar-form__layout {
    grid-template-columns: 1fr;
  }

  .ar-form__aside {
    position: static;
    order: -1;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .info-card {
    flex: 1 1 220px;
  }

  .ar-form__pipeline {
    flex-direction: column;
    align-items: stretch;
  }

  .ar-form__pipe-arrow {
    display: none;
  }
}
</style>
