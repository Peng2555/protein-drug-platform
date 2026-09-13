<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Document, UploadFilled } from '@element-plus/icons-vue'
import { createHydroRedesignJob, uploadHydroRedesignJob } from '@/api/hydroRedesign'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const EXAMPLE_FASTA = `>H
QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS
`

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const pipelineSteps = [
  { id: 'fold', label: '折抗体', desc: 'Boltz2 仅折 H / H+L' },
  { id: 'patches', label: '算斑', desc: '表面疏水 + 8 Å 聚类' },
  { id: 'enumerate', label: '枚举', desc: 'STNQA 亲水突变打分' },
  { id: 'export', label: '导出', desc: 'mutations / wetlab CSV' },
]

const name = ref('')
const fasta = ref('')
const structureFile = ref<File | null>(null)
const allowCdr = ref(false)
const allowCharged = ref(false)
const submitting = ref(false)

function onUploadChange(arg: { raw?: File }) {
  structureFile.value = arg.raw || null
}

function clearUpload() {
  structureFile.value = null
}

function fillExample() {
  fasta.value = EXAMPLE_FASTA.trim() + '\n'
}

async function submit() {
  const seq = fasta.value.trim()
  if (seq.replace(/>[^\n]*\n?/g, '').replace(/\s/g, '').length < 20) {
    ElMessage.warning('请粘贴抗体 FASTA（链 ID 为 H，可选 L）')
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: name.value.trim() || null,
      fasta: seq,
      allow_cdr: allowCdr.value,
      allow_charged: allowCharged.value,
    }
    const job = structureFile.value
      ? await uploadHydroRedesignJob(seq, structureFile.value, payload)
      : await createHydroRedesignJob(payload)
    await moduleJobs.refreshHydroRedesign()
    ElMessage.success('疏水性改造任务已提交')
    router.push({ name: 'hydro-redesign-task', params: { id: job.id } })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mp-form">
    <button type="button" class="mp-form__back" @click="router.push({ name: 'workflows' })">
      <el-icon><ArrowLeft /></el-icon>
      返回工作流
    </button>

    <header class="mp-form__hero">
      <div class="mp-form__hero-top">
        <h1>抗体疏水性改造</h1>
        <span class="mp-form__badge">第一版 · 无抗原</span>
        <span class="mp-form__meta">不重折突变体</span>
      </div>
      <p class="mp-form__desc">
        用 Boltz2 折出的抗体结构（或上传 PDB/CIF）识别表面疏水斑，再枚举亲水氨基酸替换。
        默认冻结 CDR、Cys、N/C 端各 4 位，并排除新 N-糖基化。突变体不重新折叠，斑分按 WT 该残基疏水贡献近似。
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
          <div class="field">
            <label class="field__label">任务名称</label>
            <el-input v-model="name" placeholder="例如 VHH_hydro" maxlength="128" size="large" />
          </div>

          <div class="field">
            <label class="field__label">抗体 FASTA <span class="req">*</span></label>
            <p class="field__hint">
              只接受链 ID <code>H</code> 或 <code>H</code>+<code>L</code>。单链无表头时会自动包成 &gt;H。无抗原。
              <button type="button" class="link-btn" @click="fillExample">填入示例</button>
            </p>
            <el-input
              v-model="fasta"
              type="textarea"
              :rows="10"
              placeholder=">H&#10;QVQLVESGGGLV..."
            />
          </div>

          <div class="field">
            <label class="field__label">已有结构（可选）</label>
            <p class="field__hint">上传抗体 PDB/CIF 则跳过 Boltz2；否则 GPU 折 H 或 H+L（diffusion_samples=3）。</p>
            <div v-if="structureFile" class="upload-done">
              <el-icon><Document /></el-icon>
              <span>{{ structureFile.name }}</span>
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
              <p class="upload-zone__title">拖拽或点击上传抗体结构</p>
            </el-upload>
          </div>
        </section>

        <section class="mp-section">
          <h2 class="mp-section__title">突变约束</h2>
          <p class="field__hint" style="margin-bottom: 0.85rem">
            默认保守：冻结 CDR，只用中性亲水残基。需要更大化学空间时再打开。
          </p>
          <div class="choice-grid">
            <button type="button" class="choice" :class="{ on: !allowCdr }" @click="allowCdr = false">
              <strong>冻结 CDR</strong>
              <span>推荐。框架区改疏水斑，降低结合面风险。</span>
            </button>
            <button type="button" class="choice" :class="{ on: allowCdr }" @click="allowCdr = true">
              <strong>允许改 CDR</strong>
              <span>斑落在 CDR 时才考虑；可能影响结合。</span>
            </button>
            <button type="button" class="choice" :class="{ on: !allowCharged }" @click="allowCharged = false">
              <strong>STNQA</strong>
              <span>中性亲水替换，湿实验更稳妥。</span>
            </button>
            <button type="button" class="choice" :class="{ on: allowCharged }" @click="allowCharged = true">
              <strong>STNQA + DEKR</strong>
              <span>加入带电残基，斑分下降可能更猛。</span>
            </button>
          </div>
        </section>

        <div class="actions">
          <el-button type="primary" size="large" class="actions__submit" :loading="submitting" @click="submit">
            提交改造任务
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>

      <aside class="mp-form__aside">
        <div class="info-card info-card--accent">
          <h3>打分约定</h3>
          <ul>
            <li>相对 SASA ≥ 0.25 为表面</li>
            <li>疏水残基 FILMWVY，Cβ 8 Å 聚斑</li>
            <li>排序：先 Δ斑分，再亲水分</li>
            <li>详情页会给出最终可突变位点数（冻 CDR / 端 4 位之后）</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>产物</h3>
          <ul>
            <li><code>mutations.csv</code></li>
            <li><code>wetlab.csv</code>（FR 前 20）</li>
            <li><code>patches.csv</code> / <code>pred.cif</code></li>
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
  margin-left: 0.35rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--bio-blue, #2563eb);
  font-size: 0.8rem;
  cursor: pointer;
}

.choice-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.choice {
  text-align: left;
  padding: 0.85rem 0.95rem;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: #f8fafc;
  cursor: pointer;

  strong {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.88rem;
  }

  span {
    display: block;
    font-size: 0.75rem;
    line-height: 1.45;
    color: var(--muted);
  }

  &:hover,
  &.on {
    border-color: #99f6e4;
    background: #f0fdfa;
  }

  &.on strong {
    color: #0f766e;
  }
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
