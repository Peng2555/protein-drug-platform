<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteDockingJob, fetchDockingJobs, submitDockingJob } from '@/api/docking'
import type { DockingJob } from '@/api/types'
import { statusLabel } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const name = ref('')
const receptor = ref<File | null>(null)
const ligandSmiles = ref('')
const referenceLigand = ref<File | null>(null)
const engine = ref<'vina' | 'gnina'>('vina')
const center = ref([0, 0, 0])
const size = ref([20, 20, 20])
const exhaustiveness = ref(8)
const numModes = ref(20)
const energyRange = ref(5)
const boxPadding = ref(5)
const nStarts = ref(10)
const nConformers = ref(128)
const jobs = ref<DockingJob[]>([])
const submitting = ref(false)
const activeId = computed(() => route.name === 'docking-job' ? route.params.id : null)
function changed(kind: 'receptor' | 'reference', file: { raw?: File }) {
  if (kind === 'receptor') receptor.value = file.raw ?? null
  else referenceLigand.value = file.raw ?? null
}
async function load() {
  try { jobs.value = (await fetchDockingJobs()).items ?? [] } catch { jobs.value = [] }
}
async function submit() {
  if (!receptor.value) { ElMessage.warning('请上传受体结构'); return }
  if (!ligandSmiles.value.trim()) { ElMessage.warning('请填写小分子 SMILES'); return }
  submitting.value = true
  try {
    const job = await submitDockingJob(receptor.value, ligandSmiles.value, referenceLigand.value, {
      name: name.value.trim(), engine: engine.value,
      center_x: center.value[0], center_y: center.value[1], center_z: center.value[2],
      size_x: size.value[0], size_y: size.value[1], size_z: size.value[2],
      exhaustiveness: exhaustiveness.value, num_modes: numModes.value,
      energy_range: energyRange.value, box_padding: boxPadding.value,
      n_starts: nStarts.value, n_conformers: nConformers.value,
    })
    await load()
    router.push({ name: 'docking-job', params: { id: job.id } })
    ElMessage.success('对接任务已提交')
  } catch (e) { ElMessage.error(e instanceof Error ? e.message : '提交失败') }
  finally { submitting.value = false }
}
function open(job: DockingJob) { router.push({ name: 'docking-job', params: { id: job.id } }) }
async function remove(job: DockingJob) {
  try {
    await ElMessageBox.confirm(`确定删除「${job.name || job.id.slice(0, 8)}」吗？`, '删除任务', { type: 'warning' })
    await deleteDockingJob(job.id); await load()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败') }
}
function typeOf(status: string) { return status === 'done' ? 'success' : status === 'failed' ? 'danger' : 'info' }
onMounted(() => void load())
</script>

<template>
  <div class="md-workspace">
    <aside class="md-sidebar page-card page-card--accent">
      <h3>小分子对接</h3>
      <p class="field-hint">填写 SMILES，系统用 ETKDGv3 采样构象作为起点，再做全局 Vina 搜索。不要上传配体三维文件。</p>
      <el-form label-position="top" size="small">
        <el-form-item label="任务名称"><el-input v-model="name" placeholder="可选" /></el-form-item>
        <el-form-item label="受体结构" required>
          <el-upload :auto-upload="false" :limit="1" accept=".pdb,.pdbqt,.cif,.mmcif" :on-change="(f: any) => changed('receptor', f)">
            <el-button size="small">上传 PDB / PDBQT</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="小分子 SMILES" required>
          <el-input
            v-model="ligandSmiles"
            type="textarea"
            :rows="3"
            placeholder="例如 CCO 或带立体化学的 SMILES，不要填分子式如 C2H6O"
          />
          <p class="field-hint">输入的是结构式。任何三维坐标都会丢弃，起点全部由采样生成。</p>
        </el-form-item>
        <el-form-item label="参考配体（推荐，用于自动定位口袋）">
          <el-upload :auto-upload="false" :limit="1" accept=".sdf,.mol,.mol2,.pdbqt,.pdb,.cif,.mmcif" :on-change="(f: any) => changed('reference', f)">
            <el-button size="small">上传共晶/参考配体</el-button>
          </el-upload>
          <p class="field-hint">仅用于计算搜索盒，不作为对接起点。参考配体应与受体处于同一坐标系。</p>
        </el-form-item>
        <el-form-item label="对接引擎">
          <el-select v-model="engine" style="width: 100%"><el-option label="AutoDock Vina（CPU）" value="vina" /><el-option label="GNINA（可选）" value="gnina" /></el-select>
        </el-form-item>
        <el-divider content-position="left">搜索盒中心 (x, y, z)</el-divider>
        <div class="triple"><el-input-number v-for="(_, i) in center" :key="`c${i}`" v-model="center[i]" :controls="false" /></div>
        <el-divider content-position="left">搜索盒尺寸 (x, y, z)</el-divider>
        <div class="triple"><el-input-number v-for="(_, i) in size" :key="`s${i}`" v-model="size[i]" :min="1" :controls="false" /></div>
        <el-form-item label="口袋边界扩展 (Å)">
          <el-input-number v-model="boxPadding" :min="1" :max="20" :disabled="!referenceLigand" />
          <p class="field-hint">上传参考配体后生效，默认 5 Å。</p>
        </el-form-item>
        <div class="double">
          <el-form-item label="采样构象数"><el-input-number v-model="nConformers" :min="8" :max="256" /></el-form-item>
          <el-form-item label="对接起点数"><el-input-number v-model="nStarts" :min="1" :max="10" /></el-form-item>
        </div>
        <div class="double">
          <el-form-item label="exhaustiveness"><el-input-number v-model="exhaustiveness" :min="1" :max="64" /></el-form-item>
          <el-form-item label="每起点 poses"><el-input-number v-model="numModes" :min="1" :max="50" /></el-form-item>
        </div>
        <p class="field-hint">默认 128 构象 / 10 起点 / exhaustiveness 8，与验证流程一致。起点越多越慢。</p>
        <el-button type="primary" :loading="submitting" @click="submit">提交对接</el-button>
      </el-form>
      <el-divider />
      <div v-for="job in jobs" :key="job.id" class="job-row" :class="{ active: activeId === job.id }" @click="open(job)">
        <div class="job-row-main"><strong>{{ job.name || job.id.slice(0, 8) }}</strong><el-tag size="small" :type="typeOf(job.status)">{{ statusLabel(job.status) }}</el-tag></div>
        <small>{{ job.params_json?.engine }} · {{ job.stage }}</small>
        <el-button link type="danger" size="small" @click.stop="remove(job)">删除</el-button>
      </div>
    </aside>
    <section class="md-content"><RouterView /></section>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/fold-workspace.scss';
.triple, .double { display: flex; gap: .35rem; }
.triple :deep(.el-input-number) { width: 31%; }
.double > * { width: 50%; }
.job-row { padding: .65rem 0; border-bottom: 1px solid var(--border); cursor: pointer; }
.job-row.active { background: rgba(0, 172, 161, .08); }
.job-row-main { display: flex; justify-content: space-between; gap: .5rem; }
.job-row small { color: var(--text-muted); }
</style>
