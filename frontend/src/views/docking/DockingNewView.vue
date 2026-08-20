<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { submitDockingJob, type DockMode } from '@/api/docking'
import { useModuleJobsStore } from '@/stores/moduleJobs'

const router = useRouter()
const moduleJobs = useModuleJobsStore()

const name = ref('')
const receptor = ref<File | null>(null)
const ligandSmiles = ref('')
const ligandFile = ref<File | null>(null)
const ligandTab = ref<'smiles' | 'file'>('smiles')
const referenceLigand = ref<File | null>(null)
const engine = ref<'vina' | 'gnina'>('vina')
const dockMode = ref<DockMode>('auto_blind')
const numCavities = ref(5)
const center = ref([0, 0, 0])
const size = ref([22, 22, 22])
const exhaustiveness = ref(8)
const numModes = ref(20)
const energyRange = ref(5)
const boxPadding = ref(5)
const nStarts = ref(3)
const nConformers = ref(128)
const showMore = ref(false)
const submitting = ref(false)

const modeHint = computed(() => {
  if (dockMode.value === 'auto_blind') {
    return '自动检测蛋白表面口袋，对排名靠前的口袋分别对接，再按亲和力排序（类似 CB-Dock 盲对接）。'
  }
  if (dockMode.value === 'reference') {
    return '用共晶/参考配体自动计算搜索盒，再在该口袋内对接。'
  }
  return '手动指定搜索盒中心与尺寸，适合已知活性位点。'
})

watch(dockMode, (mode) => {
  if (mode === 'auto_blind') {
    nStarts.value = Math.min(nStarts.value, 3)
    if (nStarts.value < 1) nStarts.value = 3
  }
})

function changed(kind: 'receptor' | 'reference' | 'ligand', file: { raw?: File }) {
  if (kind === 'receptor') receptor.value = file.raw ?? null
  else if (kind === 'reference') referenceLigand.value = file.raw ?? null
  else ligandFile.value = file.raw ?? null
}

async function submit() {
  if (!receptor.value) {
    ElMessage.warning('请上传蛋白（受体）结构')
    return
  }
  if (ligandTab.value === 'smiles' && !ligandSmiles.value.trim()) {
    ElMessage.warning('请填写配体 SMILES，或切换到上传配体文件')
    return
  }
  if (ligandTab.value === 'file' && !ligandFile.value) {
    ElMessage.warning('请上传配体文件，或切换到 SMILES 输入')
    return
  }
  if (dockMode.value === 'reference' && !referenceLigand.value) {
    ElMessage.warning('参考口袋模式请上传参考配体')
    return
  }
  if (
    dockMode.value === 'manual' &&
    center.value[0] === 0 &&
    center.value[1] === 0 &&
    center.value[2] === 0
  ) {
    ElMessage.warning('手动口袋模式请填写真实搜索盒中心')
    return
  }
  submitting.value = true
  try {
    const job = await submitDockingJob(
      receptor.value,
      ligandTab.value === 'smiles' ? ligandSmiles.value : '',
      ligandTab.value === 'file' ? ligandFile.value : null,
      dockMode.value === 'reference' ? referenceLigand.value : null,
      {
        name: name.value.trim(),
        engine: engine.value,
        dock_mode: dockMode.value,
        num_cavities: numCavities.value,
        center_x: center.value[0],
        center_y: center.value[1],
        center_z: center.value[2],
        size_x: size.value[0],
        size_y: size.value[1],
        size_z: size.value[2],
        exhaustiveness: exhaustiveness.value,
        num_modes: numModes.value,
        energy_range: energyRange.value,
        box_padding: boxPadding.value,
        n_starts: nStarts.value,
        n_conformers: nConformers.value,
      },
    )
    await moduleJobs.refreshDocking()
    router.push({ name: 'docking-task', params: { id: job.id } })
    ElMessage.success(dockMode.value === 'auto_blind' ? '盲对接任务已提交' : '对接任务已提交')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="docking-new page-card">
    <header class="docking-new__head">
      <h1>分子对接</h1>
      <p>
        参考 CB-Dock：上传蛋白与配体后，可自动搜索口袋并做盲对接，也可指定已知口袋。
        配体三维坐标不会作为起点，起点由构象采样生成。
      </p>
    </header>

    <div class="feature-row">
      <div class="feature">
        <strong>搜索口袋</strong>
        <span>基于蛋白表面溶剂可及网格聚类，估算候选结合腔</span>
      </div>
      <div class="feature">
        <strong>结构对接</strong>
        <span>在候选口袋内用 AutoDock Vina 搜索结合姿态</span>
      </div>
      <div class="feature">
        <strong>口袋排序</strong>
        <span>按 Vina 亲和力汇总各口袋最优结果</span>
      </div>
    </div>

    <el-form label-position="top" size="default" class="docking-form">
      <el-form-item label="任务名称">
        <el-input v-model="name" placeholder="可选，例如：TargetX–CompoundY" />
      </el-form-item>

      <div class="upload-grid">
        <section class="upload-card">
          <h3>上传蛋白</h3>
          <p class="card-hint">支持 PDB / PDBQT / CIF</p>
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            accept=".pdb,.pdbqt,.cif,.mmcif"
            :on-change="(f: { raw?: File }) => changed('receptor', f)"
          >
            <div class="upload-inner">
              <p>拖拽或点击选择蛋白文件</p>
              <p v-if="receptor" class="file-name">{{ receptor.name }}</p>
            </div>
          </el-upload>
        </section>

        <section class="upload-card">
          <h3>上传配体</h3>
          <p class="card-hint">SMILES 或 mol2 / sdf / mol / pdb</p>
          <el-radio-group v-model="ligandTab" size="small" class="ligand-tabs">
            <el-radio-button value="smiles">SMILES</el-radio-button>
            <el-radio-button value="file">上传文件</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="ligandTab === 'smiles'"
            v-model="ligandSmiles"
            type="textarea"
            :rows="5"
            placeholder="粘贴 Canonical SMILES，例如：CC(=O)Oc1ccccc1C(=O)O"
          />
          <el-upload
            v-else
            drag
            :auto-upload="false"
            :limit="1"
            accept=".sdf,.sd,.mol,.mol2,.pdb,.pdbqt,.smi,.smiles"
            :on-change="(f: { raw?: File }) => changed('ligand', f)"
          >
            <div class="upload-inner">
              <p>拖拽或点击选择配体文件</p>
              <p v-if="ligandFile" class="file-name">{{ ligandFile.name }}</p>
            </div>
          </el-upload>
        </section>
      </div>

      <el-form-item label="对接方式" class="mode-item">
        <el-radio-group v-model="dockMode">
          <el-radio value="auto_blind">自动盲对接</el-radio>
          <el-radio value="reference">参考配体定口袋</el-radio>
          <el-radio value="manual">手动指定搜索盒</el-radio>
        </el-radio-group>
        <p class="field-hint">{{ modeHint }}</p>
      </el-form-item>

      <el-form-item v-if="dockMode === 'auto_blind'" label="对接口袋数">
        <el-input-number v-model="numCavities" :min="1" :max="19" />
        <p class="field-hint">默认检测并对接排名靠前的 5 个口袋（1–19）。</p>
      </el-form-item>

      <el-form-item v-if="dockMode === 'reference'" label="参考配体（与蛋白同一坐标系）">
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".sdf,.mol,.mol2,.pdbqt,.pdb,.cif,.mmcif"
          :on-change="(f: { raw?: File }) => changed('reference', f)"
        >
          <el-button>上传共晶 / 参考配体</el-button>
        </el-upload>
      </el-form-item>

      <template v-if="dockMode === 'manual'">
        <el-divider content-position="left">搜索盒中心 (x, y, z)</el-divider>
        <div class="triple">
          <el-input-number
            v-for="(_, i) in center"
            :key="`c${i}`"
            v-model="center[i]"
            :controls="false"
          />
        </div>
        <el-divider content-position="left">搜索盒尺寸 (x, y, z)</el-divider>
        <div class="triple">
          <el-input-number
            v-for="(_, i) in size"
            :key="`s${i}`"
            v-model="size[i]"
            :min="1"
            :controls="false"
          />
        </div>
      </template>

      <el-form-item label="对接引擎">
        <el-select v-model="engine" style="width: 280px">
          <el-option label="AutoDock Vina（推荐）" value="vina" />
          <el-option label="GNINA（可选）" value="gnina" />
        </el-select>
      </el-form-item>

      <button type="button" class="more-toggle" @click="showMore = !showMore">
        {{ showMore ? '收起更多参数' : '更多参数' }}
      </button>

      <div v-show="showMore" class="more-panel">
        <el-form-item v-if="dockMode !== 'manual'" label="口袋边界扩展 (Å)">
          <el-input-number v-model="boxPadding" :min="1" :max="20" />
        </el-form-item>
        <div class="double">
          <el-form-item label="采样构象数">
            <el-input-number v-model="nConformers" :min="8" :max="256" />
          </el-form-item>
          <el-form-item label="每口袋对接起点数">
            <el-input-number v-model="nStarts" :min="1" :max="dockMode === 'auto_blind' ? 5 : 10" />
          </el-form-item>
        </div>
        <div class="double">
          <el-form-item label="exhaustiveness">
            <el-input-number v-model="exhaustiveness" :min="1" :max="64" />
          </el-form-item>
          <el-form-item label="每起点 poses">
            <el-input-number v-model="numModes" :min="1" :max="50" />
          </el-form-item>
        </div>
        <el-form-item label="energy_range (kcal/mol)">
          <el-input-number v-model="energyRange" :min="0" :max="20" :step="0.5" />
        </el-form-item>
      </div>

      <div class="submit-row">
        <el-button
          type="primary"
          size="large"
          :loading="submitting"
          @click="submit"
        >
          {{ dockMode === 'auto_blind' ? '自动盲对接' : '提交对接' }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped lang="scss">
.docking-new {
  padding: 1.15rem 1.25rem 1.6rem;
  max-width: 980px;
}

.docking-new__head {
  margin-bottom: 1rem;

  h1 {
    margin: 0;
    font-size: 1.35rem;
    color: var(--title);
  }

  p {
    margin: 0.4rem 0 0;
    font-size: 0.88rem;
    color: var(--muted);
    line-height: 1.5;
  }
}

.feature-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.feature {
  padding: 0.75rem 0.85rem;
  border: 1px solid rgba(0, 172, 161, 0.18);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(0, 172, 161, 0.06), transparent);

  strong {
    display: block;
    margin-bottom: 0.25rem;
    color: var(--bio-green-dark);
    font-size: 0.9rem;
  }

  span {
    font-size: 0.78rem;
    color: var(--muted);
    line-height: 1.4;
  }
}

.upload-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.upload-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  padding: 0.9rem 1rem 1rem;
  background: #fff;

  h3 {
    margin: 0;
    font-size: 1rem;
  }
}

.card-hint {
  margin: 0.25rem 0 0.65rem;
  color: var(--muted);
  font-size: 0.78rem;
}

.ligand-tabs {
  margin-bottom: 0.65rem;
}

.upload-inner {
  padding: 0.6rem 0.4rem;
  color: var(--muted);
  font-size: 0.86rem;
}

.file-name {
  margin-top: 0.35rem;
  color: var(--bio-blue);
  font-weight: 600;
}

.mode-item :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1rem;
}

.field-hint {
  margin: 0.35rem 0 0;
  color: var(--muted);
  font-size: 0.82rem;
}

.triple,
.double {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.triple :deep(.el-input-number) {
  width: 31%;
}

.double > * {
  flex: 1;
}

.more-toggle {
  border: none;
  background: transparent;
  color: var(--bio-blue);
  cursor: pointer;
  padding: 0;
  margin: 0.25rem 0 0.75rem;
  font-size: 0.9rem;
}

.more-panel {
  padding: 0.75rem 0.9rem;
  margin-bottom: 1rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.03);
}

.submit-row {
  margin-top: 0.5rem;
}

@media (max-width: 860px) {
  .feature-row,
  .upload-grid {
    grid-template-columns: 1fr;
  }
}
</style>
