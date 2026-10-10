<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { createTmDisulfideJob, fetchTmDisulfideSourceFoldJobs } from '@/api/tmDisulfide'
import type { TmDisulfideSourceFoldJob } from '@/api/types'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const pipelineSteps = [
  { id: 'qc', label: '质控', desc: '≥4 套 Boltz2 CIF' },
  { id: 'geometry', label: '几何', desc: 'CA/CB 与虚拟 SG' },
  { id: 'build', label: '成键', desc: 'PyRosetta Cys' },
  { id: 'energy', label: '能量', desc: '折叠态 ΔΔG 排序' },
]

const name = ref('')
const sourceJobId = ref('')
const sources = ref<TmDisulfideSourceFoldJob[]>([])
const loadingSources = ref(false)
const submitting = ref(false)

async function loadSources() {
  loadingSources.value = true
  try {
    const data = await fetchTmDisulfideSourceFoldJobs(80)
    sources.value = data.items ?? []
    if (!sourceJobId.value && sources.value.length) {
      sourceJobId.value = sources.value[0].id
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载 Boltz2 作业失败')
  } finally {
    loadingSources.value = false
  }
}

async function submit() {
  if (!sourceJobId.value) {
    ElMessage.warning('请选择一套已完成、至少 4 个模型的 Boltz2 作业')
    return
  }
  submitting.value = true
  try {
    const job = await createTmDisulfideJob({
      name: name.value.trim() || null,
      source_job_id: sourceJobId.value,
    })
    await moduleJobs.refreshTmDisulfide()
    ElMessage.success('额外二硫键任务已提交（CPU 队列）')
    router.push({ name: 'tm-disulfide-task', params: { id: job.id } })
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadSources)
</script>

<template>
  <div class="mp-form">
    <button type="button" class="mp-form__back" @click="router.push({ name: 'workflows' })">
      <el-icon><ArrowLeft /></el-icon>
      返回工作流
    </button>

    <header class="mp-form__hero">
      <div class="mp-form__hero-top">
        <h1>抗体额外二硫键</h1>
        <span class="mp-form__badge">复用 Boltz2</span>
        <span class="mp-form__meta">不在本模块内折叠</span>
      </div>
      <p class="mp-form__desc">
        选择已完成的 Boltz2 作业（至少 4 套 <code>*_model_N.cif</code>）。流水线做质控、Kabat 掩码、距离/虚拟 SG、PyRosetta 成键与折叠态能量筛选。
        不复制结构文件，只记录源作业路径。能量通过：成键且无明显 <code>fa_rep</code> 碰撞；按 ΔΔG（不含 ref）排序。
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
            <el-input v-model="name" placeholder="例如 CD38_ss" maxlength="128" size="large" />
          </div>
          <div class="field">
            <label class="field__label">源 Boltz2 作业 <span class="req">*</span></label>
            <p class="field__hint">仅列出已完成且模型数 ≥ 4 的作业。FASTA 从源作业读取。</p>
            <el-table
              v-loading="loadingSources"
              :data="sources"
              size="small"
              highlight-current-row
              max-height="360"
              @current-change="(row: TmDisulfideSourceFoldJob | null) => { if (row) sourceJobId = row.id }"
            >
              <el-table-column width="48">
                <template #default="{ row }">
                  <el-radio v-model="sourceJobId" :value="row.id" @change="sourceJobId = row.id">&nbsp;</el-radio>
                </template>
              </el-table-column>
              <el-table-column prop="name" label="名称" min-width="140">
                <template #default="{ row }">{{ row.name || row.id.slice(0, 8) }}</template>
              </el-table-column>
              <el-table-column label="模型" width="72">
                <template #default="{ row }">{{ row.n_models }}</template>
              </el-table-column>
              <el-table-column label="长度" width="80">
                <template #default="{ row }">{{ row.total_length ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="完成时间" min-width="160">
                <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!loadingSources && !sources.length" description="没有可用的 Boltz2 作业。请先在结构预测中提交 diffusion_samples ≥ 4。" />
          </div>
        </section>
        <div class="actions">
          <el-button type="primary" size="large" class="actions__submit" :loading="submitting" @click="submit">
            提交筛选
            <el-icon class="actions__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
      <aside class="mp-form__aside">
        <div class="info-card info-card--accent">
          <h3>通过规则</h3>
          <ul>
            <li>几何 / 成键 / 能量均需 ≥4 套模型通过</li>
            <li>能量：成键 + 无严重 fa_rep 碰撞</li>
            <li>表格按 median ΔΔG 升序（仅能量通过优先）</li>
          </ul>
        </div>
        <div class="info-card">
          <h3>产物</h3>
          <ul>
            <li><code>candidates.csv</code></li>
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
