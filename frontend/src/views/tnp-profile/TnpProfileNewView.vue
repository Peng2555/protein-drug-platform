<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Document, UploadFilled } from '@element-plus/icons-vue'
import { createTnpProfileBatch, createTnpProfileJob, uploadTnpProfileJob } from '@/api/tnpProfile'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const EXAMPLE_FASTA = `>H
QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS
`

const EXAMPLE_BATCH = `>nb1
QVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS
>nb2
EVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMGWFRQAPGKEREFVAAISWSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAADSSRRYDYWGQGTQVTVSS
`

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const pipelineSteps = [
  { id: 'fold', label: '折抗体', desc: 'Boltz2 仅折 VHH（H）' },
  { id: 'score', label: '计分', desc: 'Kabat 六项 + tetrad' },
  { id: 'view', label: '画像', desc: '交通灯与 CDR 附近' },
]

const mode = ref<'single' | 'batch'>('single')
const name = ref('')
const fasta = ref('')
const structureFile = ref<File | null>(null)
const submitting = ref(false)

const fastaPlaceholder = computed(() =>
  mode.value === 'batch' ? '>nb1\nQVQL...\n>nb2\nEVQL...' : '>H\nQVQLVESGGGLV...',
)
const recordCount = computed(() => {
  const text = fasta.value.trim()
  if (!text) return 0
  const headers = text.match(/^>/gm)
  if (!headers) return text.replace(/\s+/g, '').length >= 70 ? 1 : 0
  return headers.length
})

function onUploadChange(arg: { raw?: File }) {
  structureFile.value = arg.raw || null
}

function clearUpload() {
  structureFile.value = null
}

function fillExample() {
  fasta.value = (mode.value === 'batch' ? EXAMPLE_BATCH : EXAMPLE_FASTA).trim() + '\n'
}

function setMode(next: 'single' | 'batch') {
  mode.value = next
  if (next === 'batch') structureFile.value = null
}

async function submit() {
  const seq = fasta.value.trim()
  const n = recordCount.value
  if (n < 1) {
    ElMessage.warning('请粘贴完整 VHH FASTA')
    return
  }
  submitting.value = true
  try {
    const payload = { name: name.value.trim() || null, fasta: seq }
    if (mode.value === 'batch' || n > 1) {
      if (n < 2) {
        ElMessage.warning('批量至少两条 VHH，每条记录一个表头')
        submitting.value = false
        return
      }
      const created = await createTnpProfileBatch(payload)
      await moduleJobs.refreshTnpProfile()
      ElMessage.success(`已提交 ${created.job_ids.length} 条画像`)
      router.push({ name: 'tnp-profile-batch', params: { id: created.batch.id } })
      return
    }
    const job = structureFile.value
      ? await uploadTnpProfileJob(seq, structureFile.value, payload)
      : await createTnpProfileJob(payload)
    await moduleJobs.refreshTnpProfile()
    ElMessage.success('可开发性画像任务已提交')
    router.push({ name: 'tnp-profile-task', params: { id: job.id } })
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
        <h1>VHH 可开发性画像</h1>
        <span class="mp-form__badge">Boltz2 · Kabat</span>
      </div>
      <p class="mp-form__desc">
        Boltz2 折叠 VHH（也可上传已有结构），按 Kabat 计算 L、L3、C、PSH、PPC、PNC 与 tetrad，相对临床参考集给出绿 / 黄 / 红。
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
          <div class="mode-tabs" role="tablist">
            <button type="button" :class="{ active: mode === 'single' }" @click="setMode('single')">单条</button>
            <button type="button" :class="{ active: mode === 'batch' }" @click="setMode('batch')">批量</button>
          </div>
          <div class="field">
            <label class="field__label">任务名称</label>
            <el-input v-model="name" :placeholder="mode === 'batch' ? '例如 VHH_panel' : '例如 VHH_profile'" maxlength="128" size="large" />
          </div>
          <div class="field">
            <label class="field__label">VHH FASTA <span class="req">*</span></label>
            <p class="field__hint">
              <template v-if="mode === 'single'">只接受一条重链。无表头时自动包成 <code>H</code>。</template>
              <template v-else>每条记录一条 VHH，表头作为分子 ID。最多 100 条，各自独立折叠计分。</template>
              <button type="button" class="link-btn" @click="fillExample">填入示例</button>
              <span v-if="recordCount" class="count">已识别 {{ recordCount }} 条</span>
            </p>
            <el-input
              v-model="fasta"
              type="textarea"
              :rows="mode === 'batch' ? 14 : 10"
              :placeholder="fastaPlaceholder"
            />
          </div>
          <div v-if="mode === 'single'" class="field">
            <label class="field__label">已有结构（可选）</label>
            <p class="field__hint">上传 PDB/CIF 则跳过 Boltz2。残基序号需与 FASTA 一致。批量任务请不要上传结构。</p>
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
              <p class="upload-zone__title">拖拽或点击上传 VHH 结构</p>
            </el-upload>
          </div>
        </section>
        <div class="actions">
          <el-button type="primary" size="large" class="actions__submit" :loading="submitting" @click="submit">
            {{ mode === 'batch' || recordCount > 1 ? '提交批量画像' : '提交画像' }}
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
      <aside class="mp-form__aside">
        <div class="info-card info-card--accent">
          <h3>六项指标</h3>
          <ul>
            <li>L / L3：Kabat CDR 长度</li>
            <li>C：CDR3 长度 / 伸出距离</li>
            <li>PSH / PPC / PNC：CDR 附近斑分</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>Tetrad</h3>
          <p>Kabat 37 / 44 / 45 / 47，仅展示，不进交通灯。</p>
        </div>
        <div class="info-card">
          <h3>批量</h3>
          <p>多条 FASTA 会拆成独立任务并行排队，完成后可导出汇总 CSV。</p>
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
.mode-tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 1.1rem;
  padding: 0.25rem;
  width: fit-content;
  border-radius: 10px;
  background: #f3f4f6;
  button {
    border: none;
    background: transparent;
    padding: 0.35rem 0.9rem;
    border-radius: 8px;
    font-size: 0.84rem;
    font-weight: 600;
    color: var(--muted);
    cursor: pointer;
    &.active {
      background: #fff;
      color: var(--title);
    }
  }
}
.count {
  margin-left: 0.5rem;
  color: #1d4ed8;
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
  ul,
  p {
    margin: 0;
    line-height: 1.65;
  }
  ul {
    padding-left: 1.1rem;
  }
}
</style>
