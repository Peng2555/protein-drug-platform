<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Document, UploadFilled } from '@element-plus/icons-vue'
import { fetchJobs } from '@/api/jobs'
import {
  createMaskingPeptideJob,
  uploadMaskingPeptideJob,
} from '@/api/maskingPeptide'
import type { Job } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const route = useRoute()
const moduleJobs = useModuleJobsStore()

const pipelineSteps = [
  { id: 'rfdiff', label: 'RFdiffusion', desc: 'paratope 骨架采样' },
  { id: 'mpnn', label: 'MPNN + Relax', desc: '多轮序列设计与环化' },
  { id: 'export', label: '导出', desc: 'sequences_final.csv' },
]

const submitMode = ref<'fold_job' | 'upload'>('upload')
const foldJobId = ref('')
const foldOptions = ref<Job[]>([])
const antibodyFile = ref<File | null>(null)
const name = ref('')
const hotspotRes = ref('H35,H47,H50,H104,H110')
const targetChain = ref('H')
const peptideLength = ref('12-18')
const totalDesigns = ref(200)
const mpnnRounds = ref(4)
const skipBackbone = ref(false)
const relaxJobs = ref(8)
const showAdvanced = ref(false)
const submitting = ref(false)

async function loadFoldOptions() {
  try {
    const data = await fetchJobs(100, true)
    foldOptions.value = data.items.filter(
      (j) => j.status === 'done' && (j.engine === 'boltz2' || j.engine === 'esmfold2'),
    )
  } catch {
    foldOptions.value = []
  }
}

function onUploadChange(arg: { raw?: File }) {
  antibodyFile.value = arg.raw || null
}

function clearUpload() {
  antibodyFile.value = null
}

function parseHotspots(): string[] {
  return hotspotRes.value
    .split(/[\s,;]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
}

async function submit() {
  if (submitMode.value === 'fold_job' && !foldJobId.value) {
    ElMessage.warning('请选择已完成的 Boltz2 折叠任务')
    return
  }
  if (submitMode.value === 'upload' && !antibodyFile.value) {
    ElMessage.warning('请上传抗体单链 PDB（空 paratope，非复合物）')
    return
  }
  const hotspots = parseHotspots()
  if (!hotspots.length) {
    ElMessage.warning('请填写至少一个 hotspot 残基')
    return
  }

  submitting.value = true
  try {
    const body = {
      name: name.value.trim() || null,
      fold_job_id: submitMode.value === 'fold_job' ? foldJobId.value : null,
      hotspot_res: hotspots,
      target_chain: targetChain.value.trim() || 'H',
      peptide_length: peptideLength.value.trim() || '12-18',
      total_designs: totalDesigns.value,
      mpnn_rounds: mpnnRounds.value,
      skip_backbone: skipBackbone.value,
      relax_jobs: relaxJobs.value,
    }
    const job =
      submitMode.value === 'upload' && antibodyFile.value
        ? await uploadMaskingPeptideJob(antibodyFile.value, body)
        : await createMaskingPeptideJob(body)
    await moduleJobs.refreshMaskingPeptide()
    ElMessage.success('多肽遮蔽任务已提交')
    router.push({ name: 'masking-peptide-task', params: { id: job.id } })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const fold = route.query.fold_job
  if (typeof fold === 'string' && fold) {
    submitMode.value = 'fold_job'
    foldJobId.value = fold
  }
  await loadFoldOptions()
})
</script>

<template>
  <div class="mp-form">
    <button type="button" class="mp-form__back" @click="router.push({ name: 'workflows' })">
      <el-icon><ArrowLeft /></el-icon>
      返回工作流
    </button>

    <header class="mp-form__hero">
      <div class="mp-form__hero-top">
        <h1>多肽遮蔽设计</h1>
        <span class="mp-form__badge">RF + MPNN</span>
        <span class="mp-form__meta">~1–24 h</span>
      </div>
      <p class="mp-form__desc">
        在抗体 paratope 空腔处用 RFdiffusion 生成环肽骨架，再经多轮 ProteinMPNN + 环化 FastRelax
        设计序列。输入须为<strong>空 paratope 的抗体单链</strong>，勿用复合物作 RF 靶结构。
      </p>
    </header>

    <div class="mp-form__pipeline" aria-label="流水线步骤">
      <div v-for="(step, i) in pipelineSteps" :key="step.id" class="mp-form__pipe-item">
        <span class="mp-form__pipe-num">{{ i + 1 }}</span>
        <div>
          <strong>{{ step.label }}</strong>
          <span>{{ step.desc }}</span>
        </div>
        <el-icon v-if="i < pipelineSteps.length - 1" class="mp-form__pipe-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <div class="mp-form__layout">
      <div class="mp-form__main">
        <section class="mp-section">
          <h2 class="mp-section__title">抗体结构来源</h2>
          <div class="mp-form__tabs">
            <button
              type="button"
              class="mp-form__tab"
              :class="{ active: submitMode === 'upload' }"
              @click="submitMode = 'upload'"
            >
              上传单链 PDB
            </button>
            <button
              type="button"
              class="mp-form__tab"
              :class="{ active: submitMode === 'fold_job' }"
              @click="submitMode = 'fold_job'"
            >
              从 Boltz2 任务抽链
            </button>
          </div>
        </section>

        <section class="mp-section">
          <div class="field">
            <label class="field__label">任务名称</label>
            <el-input v-model="name" placeholder="例如 CD98_VHH_mask" maxlength="128" size="large" />
          </div>

          <div v-if="submitMode === 'upload'" class="field">
            <label class="field__label">抗体单链 PDB <span class="req">*</span></label>
            <p class="field__hint">空 paratope 的 VHH/Fab 重链结构，链 ID 默认 H。</p>
            <div v-if="antibodyFile" class="upload-done">
              <el-icon><Document /></el-icon>
              <span>{{ antibodyFile.name }}</span>
              <button type="button" class="link-btn" @click="clearUpload">移除</button>
            </div>
            <el-upload
              v-else
              drag
              class="upload-zone"
              :auto-upload="false"
              :limit="1"
              :show-file-list="false"
              accept=".pdb,.cif,.mmcif"
              @change="onUploadChange"
            >
              <el-icon class="upload-zone__icon"><UploadFilled /></el-icon>
              <p class="upload-zone__title">拖拽或点击上传抗体 PDB</p>
            </el-upload>
          </div>

          <div v-else class="field">
            <label class="field__label">Boltz2 折叠任务 <span class="req">*</span></label>
            <p class="field__hint">从已完成复合物中抽取目标链（默认 H）作为 RF 输入。</p>
            <el-select v-model="foldJobId" placeholder="选择已完成任务" filterable size="large" style="width: 100%">
              <el-option
                v-for="j in foldOptions"
                :key="j.id"
                :label="`${j.name || j.id.slice(0, 8)}${j.iptm != null ? ` · ipTM=${j.iptm.toFixed(2)}` : ''}`"
                :value="j.id"
              />
            </el-select>
          </div>

          <div class="field">
            <label class="field__label">Hotspot 残基 <span class="req">*</span></label>
            <p class="field__hint">RFdiffusion ppi.hotspot_res，逗号分隔（CD98 默认五残基）。</p>
            <el-input v-model="hotspotRes" placeholder="H35,H47,H50,H104,H110" size="large" />
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field__label">目标链 ID</label>
              <el-input v-model="targetChain" placeholder="H" maxlength="8" />
            </div>
            <div class="field">
              <label class="field__label">肽段长度</label>
              <el-input v-model="peptideLength" placeholder="12-18" />
            </div>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="field__label">骨架数量 total_designs</label>
              <el-input-number v-model="totalDesigns" :min="10" :max="20000" :step="50" style="width: 100%" />
              <p class="field__hint">试跑 200；规模生产 20000。</p>
            </div>
            <div class="field">
              <label class="field__label">MPNN 轮数</label>
              <el-input-number v-model="mpnnRounds" :min="1" :max="8" style="width: 100%" />
            </div>
          </div>
        </section>

        <section class="mp-section mp-section--muted">
          <button type="button" class="optional-toggle" @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '▾' : '▸' }} 高级选项
          </button>
          <div v-show="showAdvanced" class="advanced-box">
            <el-checkbox v-model="skipBackbone">跳过 RFdiffusion（复用已有骨架目录）</el-checkbox>
            <div class="field" style="margin-top: 0.75rem">
              <label class="field__label">Relax 并行数</label>
              <el-input-number v-model="relaxJobs" :min="1" :max="32" />
            </div>
          </div>
        </section>

        <div class="actions">
          <el-button type="primary" size="large" class="actions__submit" :loading="submitting" @click="submit">
            提交设计任务
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <aside class="mp-form__aside">
        <div class="info-card info-card--accent">
          <h3>输入要求</h3>
          <ul>
            <li>抗体须已去除 paratope 配体/肽段</li>
            <li>勿将抗体–抗原复合物直接作 RF 靶</li>
            <li>Hotspot 对应 paratope 界面残基</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>产物</h3>
          <ul>
            <li><code>sequences_final.csv</code></li>
            <li><code>structures.zip</code>（末轮 merged PDB）</li>
            <li><code>summary.json</code></li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped lang="scss">
.mp-form {
  max-width: 1080px;
  margin: 0 auto;
  padding: 1.25rem 1.5rem 2.5rem;
}

.mp-form__back {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--muted);
  font-size: 0.82rem;
  cursor: pointer;

  &:hover {
    color: var(--bio-green, #00aca1);
  }
}

.mp-form__hero {
  margin-bottom: 1.25rem;

  h1 {
    margin: 0;
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
}

.mp-form__hero-top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-bottom: 0.5rem;
}

.mp-form__badge {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #0f766e;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
}

.mp-form__meta {
  font-size: 0.78rem;
  color: var(--muted);
}

.mp-form__desc {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.65;
  color: var(--body);
  max-width: 720px;
}

.mp-form__pipeline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.35rem;
  margin-bottom: 1.5rem;
  padding: 0.85rem 1rem;
  border-radius: 14px;
  background: linear-gradient(135deg, #f0fdfa 0%, #eff6ff 100%);
  border: 1px solid #e5e7eb;
}

.mp-form__pipe-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.78rem;

  strong {
    display: block;
    font-size: 0.82rem;
  }

  span {
    color: var(--muted);
  }
}

.mp-form__pipe-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.68rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--bio-green, #00aca1), var(--bio-blue, #2563eb));
}

.mp-form__pipe-arrow {
  color: #9ca3af;
  margin: 0 0.15rem;
}

.mp-form__layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 1.5rem;
  align-items: start;

  @media (max-width: 900px) {
    grid-template-columns: 1fr;
  }
}

.mp-section {
  padding: 1.25rem 1.35rem;
  margin-bottom: 1rem;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: #fff;

  &--muted {
    background: var(--bg-soft);
  }
}

.mp-section__title {
  margin: 0 0 0.85rem;
  font-size: 0.95rem;
  font-weight: 700;
}

.mp-form__tabs {
  display: flex;
  gap: 0.5rem;
}

.mp-form__tab {
  flex: 1;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-soft);
  font-size: 0.82rem;
  cursor: pointer;
  transition: all 0.15s ease;

  &.active {
    border-color: var(--bio-green, #00aca1);
    background: #ecfdf5;
    color: #0f766e;
    font-weight: 600;
  }
}

.field {
  margin-bottom: 1rem;

  &__label {
    display: block;
    margin-bottom: 0.35rem;
    font-size: 0.85rem;
    font-weight: 600;
  }

  &__hint {
    margin: 0 0 0.5rem;
    font-size: 0.78rem;
    color: var(--muted);
    line-height: 1.5;
  }
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;

  @media (max-width: 600px) {
    grid-template-columns: 1fr;
  }
}

.req {
  color: #dc2626;
}

.upload-done {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  font-size: 0.85rem;
}

.upload-zone {
  width: 100%;

  :deep(.el-upload-dragger) {
    padding: 1.5rem;
    border-radius: 12px;
  }
}

.upload-zone__icon {
  font-size: 2rem;
  color: var(--bio-green, #00aca1);
}

.upload-zone__title {
  margin: 0.5rem 0 0;
  font-size: 0.88rem;
}

.link-btn {
  margin-left: auto;
  padding: 0;
  border: none;
  background: none;
  color: var(--bio-blue, #2563eb);
  font-size: 0.8rem;
  cursor: pointer;
}

.optional-toggle {
  padding: 0;
  border: none;
  background: none;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--body);
}

.advanced-box {
  margin-top: 0.75rem;
}

.actions {
  margin-top: 0.5rem;

  &__submit {
    min-width: 200px;
  }

  &__arrow {
    margin-left: 0.35rem;
  }
}

.info-card {
  padding: 1rem 1.1rem;
  margin-bottom: 0.85rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #fff;
  font-size: 0.82rem;

  &--accent {
    border-color: #a7f3d0;
    background: #f0fdf4;
  }

  h3 {
    margin: 0 0 0.55rem;
    font-size: 0.88rem;
  }

  ul {
    margin: 0;
    padding-left: 1.1rem;
    line-height: 1.65;
    color: var(--body);
  }

  code {
    font-size: 0.78rem;
  }
}
</style>
