<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Document, UploadFilled } from '@element-plus/icons-vue'
import { createCicProfileJob, uploadCicProfileJob } from '@/api/cicProfile'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const EXAMPLE_FASTA = `>H
QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS
`

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const pipelineSteps = [
  { id: 'fold', label: '折抗体', desc: 'Boltz2 仅折 H / H+L' },
  { id: 'patches', label: '算斑', desc: '正电 / 负电 / 疏水 8 Å' },
  { id: 'view', label: '3D', desc: '分子表面着色展示' },
]

const name = ref('')
const fasta = ref('')
const ph = ref(7)
const structureFile = ref<File | null>(null)
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
    const payload = { name: name.value.trim() || null, fasta: seq, ph: ph.value }
    const job = structureFile.value
      ? await uploadCicProfileJob(seq, structureFile.value, payload)
      : await createCicProfileJob(payload)
    await moduleJobs.refreshCicProfile()
    ElMessage.success('CIC 表面斑任务已提交')
    router.push({ name: 'cic-profile-task', params: { id: job.id } })
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
        <h1>抗体 CIC 表面斑</h1>
        <span class="mp-form__badge">第一版 · 诊断</span>
        <span class="mp-form__meta">尚无 APBS / 突变优化</span>
      </div>
      <p class="mp-form__desc">
        按给定 CIC 实验 pH 给可电离残基分配有效电荷（Henderson–Hasselbalch），再识别表面正电斑、负电斑与疏水斑，并在分子表面上着色。
        第一版不做 PDB2PQR/APBS，也不改序列。
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
            <el-input v-model="name" placeholder="例如 VHH_cic" maxlength="128" size="large" />
          </div>
          <div class="field">
            <label class="field__label">CIC 实验 pH</label>
            <p class="field__hint">默认 7.0。His 电荷对 pH 最敏感。</p>
            <el-input-number v-model="ph" :min="4" :max="10" :step="0.1" :precision="1" />
          </div>
          <div class="field">
            <label class="field__label">抗体 FASTA <span class="req">*</span></label>
            <p class="field__hint">
              只接受链 ID <code>H</code> 或 <code>H</code>+<code>L</code>。
              <button type="button" class="link-btn" @click="fillExample">填入示例</button>
            </p>
            <el-input v-model="fasta" type="textarea" :rows="10" placeholder=">H&#10;QVQLVESGGGLV..." />
          </div>
          <div class="field">
            <label class="field__label">已有结构（可选）</label>
            <p class="field__hint">上传抗体 PDB/CIF 则跳过 Boltz2。</p>
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
        <div class="actions">
          <el-button type="primary" size="large" class="actions__submit" :loading="submitting" @click="submit">
            提交 CIC 分析
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
      <aside class="mp-form__aside">
        <div class="info-card info-card--accent">
          <h3>第一版打分</h3>
          <ul>
            <li>正/负电：有效电荷 × SASA，RSA ≥ 0.20</li>
            <li>疏水：WFYLIVM，RSA ≥ 0.25</li>
            <li>Cβ 8 Å 聚斑</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>产物</h3>
          <ul>
            <li><code>patches.csv</code></li>
            <li><code>residue_features.csv</code></li>
            <li><code>pred.cif</code></li>
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
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
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
  background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
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
  background: linear-gradient(135deg, #2563eb, #0f766e);
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
  color: #2563eb;
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
    border-color: #bfdbfe;
    background: #eff6ff;
  }
  h3 {
    margin: 0 0 0.55rem;
    font-size: 0.88rem;
  }
  ul {
    margin: 0;
    padding-left: 1.1rem;
    line-height: 1.65;
  }
}
</style>
