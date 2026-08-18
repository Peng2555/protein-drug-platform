<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteSynthesisJob,
  fetchSynthesisJobs,
  runSynthesisJob,
} from '@/api/synthesis'
import type { SynthesisJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const router = useRouter()
const route = useRoute()

const jobName = ref('')
const shmFile = ref<File | null>(null)
const iggmFile = ref<File | null>(null)
const originFile = ref<File | null>(null)
const minSeqCount = ref(30)
const minExtraCount = ref(100)
const vGene = ref('')
const chainId = ref('H')
const submitting = ref(false)
const jobs = ref<SynthesisJob[]>([])

const activeId = computed(() =>
  route.name === 'synthesis-job' ? (route.params.id as string) : null,
)

async function loadList() {
  try {
    const data = await fetchSynthesisJobs(50)
    jobs.value = data.items ?? []
  } catch {
    jobs.value = []
  }
}

function onShmChange(f: { raw?: File }) {
  shmFile.value = f.raw ?? null
}

function onIggmChange(f: { raw?: File }) {
  iggmFile.value = f.raw ?? null
}

function onOriginChange(f: { raw?: File }) {
  originFile.value = f.raw ?? null
}

async function submit() {
  if (!shmFile.value) {
    ElMessage.warning('请上传 SHM 测序大表')
    return
  }
  if (!iggmFile.value) {
    ElMessage.warning('请上传 IgGM CDR3 突变表 (cdr3_all_1to3.csv)')
    return
  }
  submitting.value = true
  try {
    const result = await runSynthesisJob(shmFile.value, iggmFile.value, {
      name: jobName.value.trim() || null,
      originFasta: originFile.value,
      min_seq_count: minSeqCount.value,
      min_extra_count: minExtraCount.value,
      chain_id: chainId.value,
      v_gene: vGene.value.trim() || undefined,
    })
    jobName.value = ''
    shmFile.value = null
    iggmFile.value = null
    originFile.value = null
    await loadList()
    router.push({ name: 'synthesis-job', params: { id: result.job_id! } })
    ElMessage.success(
      `筛选完成：匹配 ${result.matched_count} 行，送合成 ${result.order_count} 条（A ${result.a_count} / B ${result.b_count}）`,
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '筛选失败')
  } finally {
    submitting.value = false
  }
}

function openJob(job: SynthesisJob) {
  router.push({ name: 'synthesis-job', params: { id: job.id } })
}

async function onDelete(job: SynthesisJob) {
  const label = job.name || job.id.slice(0, 8)
  try {
    await ElMessageBox.confirm(`确定删除「${label}」吗？`, '删除', { type: 'warning' })
    await deleteSynthesisJob(job.id)
    if (activeId.value === job.id) router.push({ name: 'synthesis' })
    await loadList()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusTagType(status: string) {
  if (status === 'done') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

onMounted(() => {
  void loadList()
})
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>合成候选筛选</h3>
      <el-form label-position="top" size="small">
        <el-form-item label="任务名称（可选）">
          <el-input v-model="jobName" placeholder="如 CD200R_round1" />
        </el-form-item>

        <el-form-item label="SHM 测序大表" required>
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".csv,.tsv,.xlsx,.xls"
            :on-change="onShmChange"
            :on-remove="() => (shmFile = null)"
          >
            <el-button size="small">选择 SHM 大表</el-button>
          </el-upload>
          <p class="field-hint">需含 kabat_FR1…kabat_FR4 与 kabat_CDR3 列</p>
        </el-form-item>

        <el-form-item label="IgGM CDR3 突变表" required>
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".csv,.tsv,.xlsx,.xls"
            :on-change="onIggmChange"
            :on-remove="() => (iggmFile = null)"
          >
            <el-button size="small">选择 cdr3_all_1to3.csv</el-button>
          </el-upload>
        </el-form-item>

        <el-form-item label="母本 origin.fasta（可选）">
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".fasta,.fa,.faa"
            :on-change="onOriginChange"
            :on-remove="() => (originFile = null)"
          >
            <el-button size="small">选择 origin.fasta</el-button>
          </el-upload>
          <p class="field-hint">用于在 SHM 表中定位母本参考行；不上传则取最高 count 行</p>
        </el-form-item>

        <el-divider content-position="left">筛选参数</el-divider>

        <div class="inline-fields">
          <el-form-item label="重链 ID">
            <el-input v-model="chainId" style="width: 70px" />
          </el-form-item>
          <el-form-item label="v_gene（可选）">
            <el-input v-model="vGene" placeholder="自动识别" />
          </el-form-item>
        </div>
        <div class="inline-fields">
          <el-form-item label="SHM 最低 count">
            <el-input-number v-model="minSeqCount" :min="0" :max="999999" />
          </el-form-item>
          <el-form-item label="B档最低 count">
            <el-input-number v-model="minExtraCount" :min="0" :max="999999" />
          </el-form-item>
        </div>

        <el-button type="primary" size="small" :loading="submitting" @click="submit">
          运行筛选
        </el-button>
      </el-form>

      <div class="task-list-section">
        <div class="task-list-head">
          <h3>筛选记录</h3>
          <el-button size="small" text @click="loadList">刷新</el-button>
        </div>
        <div v-if="!jobs.length" class="empty-state">暂无记录</div>
        <div v-else class="task-list">
          <div
            v-for="j in jobs"
            :key="j.id"
            class="job-item task-item"
            :class="{ active: activeId === j.id }"
            @click="openJob(j)"
          >
            <div class="job-item-top">
              <div class="title">
                <span class="task-kind-badge kind-syn">合成</span>
                {{ j.name || j.id.slice(0, 8) }}
              </div>
              <div class="job-item-actions" @click.stop>
                <el-tag :type="statusTagType(j.status)" size="small">
                  {{ statusLabel(j.status) }}
                </el-tag>
                <button type="button" class="job-delete-btn" @click="onDelete(j)">×</button>
              </div>
            </div>
            <div class="meta">
              <template v-if="j.results_json">
                匹配 {{ (j.results_json as Record<string, number>).matched_count ?? '—' }}
                · 送合成 {{ (j.results_json as Record<string, number>).order_count ?? '—' }}
              </template>
              · {{ formatTime(j.created_at) }}
            </div>
          </div>
        </div>
      </div>
    </aside>

    <div class="fold-main">
      <RouterView />
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';

.kind-syn {
  background: #e0f2fe;
  color: #0369a1;
}

.inline-fields {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.field-hint {
  margin: 0.35rem 0 0;
  font-size: 0.75rem;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

h3 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  color: var(--title);
}
</style>
