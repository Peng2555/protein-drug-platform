<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus } from '@element-plus/icons-vue'
import { createJob } from '@/api/jobs'
import { createVhhPanel } from '@/api/batches'
import BoltzChainBuilder, {
  type ChainEntity,
} from '@/components/fold/BoltzChainBuilder.vue'
import { useFoldTasksStore } from '@/stores/foldTasks'
import { EXAMPLE_FASTA } from '@/utils/constants'
import { importHeavyChainFile, parseHeavyChainText, type HeavyChainRow } from '@/utils/heavyChain'

const router = useRouter()
const store = useFoldTasksStore()

const submitTab = ref<'single' | 'batch'>('single')
const heavyTab = ref<'csv' | 'fasta'>('csv')
const showOptional = ref(true)
const showRestraints = ref(true)

const jobName = ref('')

type RestraintRow =
  | {
      key: string
      type: 'pocket'
      binder: string
      contactsText: string
      max_distance: number
      force: boolean
    }
  | {
      key: string
      type: 'contact'
      token1Text: string
      token2Text: string
      max_distance: number
      force: boolean
    }

function newEntity(partial?: Partial<ChainEntity>): ChainEntity {
  return {
    key: `c_${Math.random().toString(36).slice(2, 9)}`,
    entity: 'protein',
    copies: 1,
    ids: ['A'],
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
  newEntity({ ids: ['A'], key: 'c_init_a' }),
  newEntity({ ids: ['B'], key: 'c_init_b', copies: 1 }),
])

// 重新编号 A,B
;(() => {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  let i = 0
  for (const e of chainEntities.value) {
    e.ids = [letters[i]!]
    i += 1
  }
})()

const restraints = ref<RestraintRow[]>([])
const affinityEnabled = ref(false)
const affinityBinder = ref('')

const batchName = ref('')
const targetName = ref('')
const targetSeq = ref('')
const targetChainId = ref('A')
const heavyChainId = ref('H')
const heavyCsvInput = ref('')
const heavyFastaInput = ref('')
const heavyFileHint = ref('')

const foldEngine = ref<'boltz2' | 'esmfold2'>('boltz2')
const esmLoops = ref(3)
const esmSteps = ref(200)
const esmSamples = ref(1)

const boltz = reactive({
  recycling_steps: 3,
  sampling_steps: 200,
  diffusion_samples: 1,
  max_parallel_samples: 5,
  step_scale: null as number | null,
  seed: null as number | null,
  output_format: 'mmcif' as 'mmcif' | 'pdb',
  model: 'boltz2' as 'boltz2' | 'boltz1',
  method: '',
  use_potentials: false,
  use_msa_server: true,
  msa_pairing_strategy: 'greedy' as 'greedy' | 'complete',
  max_msa_seqs: 8192,
  subsample_msa: false,
  num_subsampled_msa: 1024,
  write_full_pae: false,
  write_full_pde: false,
  write_embeddings: false,
})

const submitting = ref(false)
const lastStatus = ref('')

const heavyPreview = computed(() => {
  const text = heavyTab.value === 'fasta' ? heavyFastaInput.value : heavyCsvInput.value
  return parseHeavyChainText(text).rows
})

const ligandChainIds = computed(() =>
  chainEntities.value.filter((e) => e.entity === 'ligand').flatMap((e) => e.ids),
)

const allChainIds = computed(() => chainEntities.value.flatMap((e) => e.ids))

watch(ligandChainIds, (ids) => {
  if (affinityEnabled.value && ids.length && !ids.includes(affinityBinder.value)) {
    affinityBinder.value = ids[0] || ''
  }
  if (!ids.length) {
    affinityEnabled.value = false
    affinityBinder.value = ''
  }
})

function getHeavyChains(): HeavyChainRow[] {
  const text = heavyTab.value === 'fasta' ? heavyFastaInput.value : heavyCsvInput.value
  return parseHeavyChainText(text).rows
}

async function onHeavyFileChange(uploadFile: { raw?: File } | File) {
  const file = uploadFile instanceof File ? uploadFile : uploadFile.raw
  if (!file) return
  try {
    const data = await importHeavyChainFile(file)
    if (data.format === 'fasta') {
      heavyFastaInput.value = data.text
      heavyCsvInput.value = ''
      heavyTab.value = 'fasta'
    } else {
      heavyCsvInput.value = data.text
      heavyFastaInput.value = ''
      heavyTab.value = 'csv'
    }
    heavyFileHint.value = data.row_count
      ? `已导入 ${file.name}（${data.encoding}）· 识别 ${data.row_count} 条重链`
      : `已读取 ${file.name}，但未解析到有效重链`
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入失败')
  }
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
      id = line.slice(1).split(/\s+/)[0] || 'A'
      parts = []
    } else {
      parts.push(line)
    }
  }
  if (id != null) blocks.push({ id, seq: parts.join('') })
  if (!blocks.length) return [newEntity()]
  return blocks.map((b, i) =>
    newEntity({
      key: `ex_${i}`,
      entity: 'protein',
      copies: 1,
      ids: [b.id.slice(0, 4)],
      sequence: b.seq,
    }),
  )
}

function loadExample() {
  chainEntities.value = parseFastaToEntities(EXAMPLE_FASTA)
  // 规范化为 A/B
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  chainEntities.value.forEach((e, i) => {
    e.ids = [letters[i] || `X${i}`]
    e.copies = 1
  })
  jobName.value = 'vhh_lysozyme_demo'
  restraints.value = []
  affinityEnabled.value = false
}

function randomizeSeed() {
  boltz.seed = Math.floor(Math.random() * 2_147_483_647)
}

function clearSeed() {
  boltz.seed = null
}

function boltzParamsPayload() {
  return {
    recycling_steps: boltz.recycling_steps,
    sampling_steps: boltz.sampling_steps,
    diffusion_samples: boltz.diffusion_samples,
    max_parallel_samples: boltz.max_parallel_samples,
    step_scale: boltz.step_scale,
    seed: boltz.seed,
    output_format: boltz.output_format,
    model: boltz.model,
    method: boltz.method.trim() || null,
    use_potentials: boltz.use_potentials,
    use_msa_server: boltz.use_msa_server,
    msa_pairing_strategy: boltz.msa_pairing_strategy,
    max_msa_seqs: boltz.max_msa_seqs,
    subsample_msa: boltz.subsample_msa,
    num_subsampled_msa: boltz.num_subsampled_msa,
    write_full_pae: boltz.write_full_pae,
    write_full_pde: boltz.write_full_pde,
    write_embeddings: boltz.write_embeddings,
  }
}

function buildComponents() {
  return chainEntities.value.map((e) => {
    if (e.entity === 'ligand') {
      return {
        entity: 'ligand' as const,
        ids: e.ids,
        smiles: e.ligandMode === 'smiles' ? e.smiles.trim() : null,
        ccd: e.ligandMode === 'ccd' ? e.ccd.trim() : null,
        cyclic: false,
        modifications: [],
      }
    }
    return {
      entity: e.entity,
      ids: e.ids,
      sequence: e.sequence.replace(/\s/g, ''),
      cyclic: e.cyclic,
      modifications: e.modifications
        .filter((m) => m.ccd.trim())
        .map((m) => ({ position: m.position, ccd: m.ccd.trim() })),
    }
  })
}

function parseToken(text: string): [string, number] {
  const parts = text.split(/[,:\s]+/).filter(Boolean)
  if (parts.length < 2) throw new Error(`残基格式应为「链ID,残基号」，当前：${text}`)
  const res = Number(parts[1])
  if (!Number.isFinite(res) || res < 1) throw new Error(`无效残基号：${text}`)
  return [parts[0]!, res]
}

function buildConstraints() {
  return restraints.value.map((r) => {
    if (r.type === 'pocket') {
      const contacts = r.contactsText
        .split(/;|\n/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map(parseToken)
      if (!contacts.length) throw new Error('口袋约束至少需要一个 contact 残基')
      return {
        type: 'pocket' as const,
        binder: r.binder,
        contacts,
        max_distance: r.max_distance,
        force: r.force,
      }
    }
    return {
      type: 'contact' as const,
      token1: parseToken(r.token1Text),
      token2: parseToken(r.token2Text),
      max_distance: r.max_distance,
      force: r.force,
    }
  })
}

function addPocketRestraint() {
  restraints.value.push({
    key: `r_${Math.random().toString(36).slice(2, 8)}`,
    type: 'pocket',
    binder: ligandChainIds.value[0] || allChainIds.value[0] || 'B',
    contactsText: 'A,100',
    max_distance: 6,
    force: false,
  })
}

function addContactRestraint() {
  restraints.value.push({
    key: `r_${Math.random().toString(36).slice(2, 8)}`,
    type: 'contact',
    token1Text: 'A,10',
    token2Text: 'B,20',
    max_distance: 6,
    force: false,
  })
}

function removeRestraint(i: number) {
  restraints.value.splice(i, 1)
}

function validateEntities(): string | null {
  if (!chainEntities.value.length) return '请至少添加一条链'
  for (const e of chainEntities.value) {
    if (e.entity === 'ligand') {
      if (e.ligandMode === 'smiles' && !e.smiles.trim()) return `配体链 ${e.ids.join(',')} 缺少 SMILES`
      if (e.ligandMode === 'ccd' && !e.ccd.trim()) return `配体链 ${e.ids.join(',')} 缺少 CCD`
    } else if (!e.sequence.replace(/\s/g, '')) {
      return `链 ${e.ids.join(',')} 序列为空`
    }
  }
  if (affinityEnabled.value) {
    if (!affinityBinder.value) return '请选择亲和力预测的小分子 binder 链'
    if (!ligandChainIds.value.includes(affinityBinder.value)) {
      return '亲和力 binder 必须是小分子配体链（Boltz-2 不支持蛋白–蛋白亲和力）'
    }
  }
  return null
}

async function submitSingle() {
  const err = validateEntities()
  if (err) {
    ElMessage.warning(err)
    return
  }
  submitting.value = true
  lastStatus.value = '正在提交单条预测…'
  try {
    const engine = foldEngine.value
    let constraintsPayload: ReturnType<typeof buildConstraints> = []
    try {
      constraintsPayload = engine === 'boltz2' ? buildConstraints() : []
    } catch (e) {
      ElMessage.warning(e instanceof Error ? e.message : '约束格式错误')
      submitting.value = false
      return
    }

    const components = buildComponents()
    const job = await createJob({
      name: jobName.value.trim() || null,
      engine,
      use_msa_server: engine === 'boltz2' ? boltz.use_msa_server : false,
      components,
      ...(engine === 'boltz2'
        ? {
            boltz_params: boltzParamsPayload(),
            constraints: constraintsPayload,
            affinity:
              affinityEnabled.value && affinityBinder.value
                ? { binder: affinityBinder.value }
                : null,
          }
        : {}),
      ...(engine === 'esmfold2'
        ? {
            esmfold_params: {
              num_loops: esmLoops.value,
              num_sampling_steps: esmSteps.value,
              num_diffusion_samples: esmSamples.value,
            },
          }
        : {}),
    })
    await store.refreshFoldTasks()
    store.startPolling()
    lastStatus.value = `已提交「${job.name || job.id.slice(0, 8)}」，状态：${job.status}`
    ElMessage.success('任务已提交')
    router.push({ name: 'fold-task', params: { id: job.id } })
  } catch (e) {
    lastStatus.value = e instanceof Error ? e.message : '提交失败'
    ElMessage.error(lastStatus.value)
  } finally {
    submitting.value = false
  }
}

async function submitBatch() {
  const chains = getHeavyChains()
  if (!targetName.value.trim()) {
    ElMessage.warning('请填写靶点名称')
    return
  }
  if (!targetSeq.value.trim()) {
    ElMessage.warning('请填写抗原序列')
    return
  }
  if (!chains.length) {
    ElMessage.warning('请提供至少一条重链（CSV 或 FASTA）')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认提交批量预测？\n\n靶点：${targetName.value}\n重链数：${chains.length}\n\n任务将依次排队运行。`,
      '批量预测',
      { type: 'info' },
    )
  } catch {
    return
  }

  submitting.value = true
  lastStatus.value = '正在提交批量预测…'
  try {
    const engine = foldEngine.value
    const data = await createVhhPanel({
      batch_name: batchName.value.trim() || null,
      target: {
        name: targetName.value.trim(),
        chain_id: targetChainId.value.trim() || 'A',
        sequence: targetSeq.value.replace(/\s/g, ''),
      },
      heavy_chain_id: heavyChainId.value.trim() || 'H',
      heavy_chains: chains,
      engine,
      use_msa_server: engine === 'boltz2' ? boltz.use_msa_server : false,
      ...(engine === 'boltz2' ? { boltz_params: boltzParamsPayload() } : {}),
      ...(engine === 'esmfold2'
        ? {
            esmfold_params: {
              num_loops: esmLoops.value,
              num_sampling_steps: esmSteps.value,
              num_diffusion_samples: esmSamples.value,
            },
          }
        : {}),
    })
    let note = `已创建批次「${data.batch.name}」，共 ${data.job_ids.length} 个任务。`
    if (data.skipped_duplicates) note += `（跳过 ${data.skipped_duplicates} 条重复序列）`
    lastStatus.value = note
    ElMessage.success(note)
    heavyCsvInput.value = ''
    heavyFastaInput.value = ''
    heavyFileHint.value = ''
    await store.refreshFoldTasks()
    store.startPolling()
    router.push({ name: 'fold-batch', params: { id: data.batch.id } })
  } catch (e) {
    if (e !== 'cancel') {
      lastStatus.value = e instanceof Error ? e.message : '提交失败'
      ElMessage.error(lastStatus.value)
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="boltz-form">
    <button type="button" class="boltz-form__back" @click="router.push({ name: 'app' })">
      <el-icon><ArrowLeft /></el-icon>
      返回工具目录
    </button>

    <header class="boltz-form__hero">
      <div class="boltz-form__hero-top">
        <h1>Boltz-2</h1>
        <span class="boltz-form__badge">结构预测</span>
        <span class="boltz-form__meta">~5–30 min</span>
      </div>
      <p class="boltz-form__desc">
        AlphaFold3 同系复合物预测：蛋白 / 多肽 / 核酸 / 小分子共折叠。也可切换 ESMFold2 做快速折叠。
      </p>
    </header>

    <div class="boltz-form__tabs">
      <button
        type="button"
        class="boltz-form__tab"
        :class="{ active: submitTab === 'single' }"
        @click="submitTab = 'single'"
      >
        单条预测
      </button>
      <button
        type="button"
        class="boltz-form__tab"
        :class="{ active: submitTab === 'batch' }"
        @click="submitTab = 'batch'"
      >
        VHH 批量
      </button>
    </div>

    <!-- 单条 -->
    <div v-show="submitTab === 'single'" class="boltz-form__body">
      <div class="field">
        <label class="field__label">任务名称</label>
        <p class="field__hint">可选。便于在任务列表中检索；留空则按链组成自动命名。</p>
        <el-input v-model="jobName" placeholder="例如 vhh_demo / 8JYR_complex" />
      </div>

      <div class="field">
        <label class="field__label">预测引擎</label>
        <p class="field__hint">Boltz-2 适合高精度复合物；ESMFold2 更快，适合大批量筛选。</p>
        <el-radio-group v-model="foldEngine">
          <el-radio-button value="boltz2">Boltz-2</el-radio-button>
          <el-radio-button value="esmfold2">ESMFold2</el-radio-button>
        </el-radio-group>
      </div>

      <div class="field">
        <div class="field__row">
          <label class="field__label">序列 / 分子</label>
          <button type="button" class="link-btn" @click="loadExample">加载示例</button>
        </div>
        <p class="field__hint">
          用 Add chain 添加多条链；Copies 表示相同序列的拷贝数（写入 YAML 为 id: [A, B]）。Boltz 链 ID ≤ 4
          字符。
        </p>
        <BoltzChainBuilder
          v-model="chainEntities"
          :allow-ligand="foldEngine === 'boltz2'"
        />
      </div>

      <template v-if="foldEngine === 'boltz2'">
        <div class="field">
          <div class="field__row">
            <label class="field__label">约束（Restraints）</label>
            <button type="button" class="link-btn" @click="showRestraints = !showRestraints">
              {{ showRestraints ? '收起' : '展开' }}
            </button>
          </div>
          <p class="field__hint">
            用先验接触信息约束链间排布：口袋（pocket）指定 binder 靠近哪些残基；接触（contact）指定两残基靠近。
          </p>
          <div v-show="showRestraints" class="restraint-box">
            <div v-for="(r, ri) in restraints" :key="r.key" class="restraint-card">
              <div class="restraint-card__head">
                <strong>{{ r.type === 'pocket' ? 'Pocket' : 'Contact' }}</strong>
                <button type="button" class="link-btn" @click="removeRestraint(ri)">删除</button>
              </div>
              <template v-if="r.type === 'pocket'">
                <label class="mini-label">Binder 链</label>
                <el-select v-model="r.binder" style="width: 120px">
                  <el-option v-for="id in allChainIds" :key="id" :label="id" :value="id" />
                </el-select>
                <label class="mini-label">Contacts（每行或分号：链ID,残基号）</label>
                <el-input
                  v-model="r.contactsText"
                  type="textarea"
                  :rows="2"
                  placeholder="A,829&#10;A,138"
                />
              </template>
              <template v-else>
                <label class="mini-label">Token1 / Token2（链ID,残基号）</label>
                <div class="inline">
                  <el-input v-model="r.token1Text" placeholder="A,10" style="width: 140px" />
                  <el-input v-model="r.token2Text" placeholder="B,20" style="width: 140px" />
                </div>
              </template>
              <div class="inline mt">
                <span class="mini-label">max distance (Å)</span>
                <el-input-number v-model="r.max_distance" :min="4" :max="20" :step="0.5" />
                <el-checkbox v-model="r.force">Force（势函数强制）</el-checkbox>
              </div>
            </div>
            <div class="inline">
              <button type="button" class="add-chain-mini" @click="addPocketRestraint">
                <el-icon><Plus /></el-icon>
                Add pocket
              </button>
              <button type="button" class="add-chain-mini" @click="addContactRestraint">
                <el-icon><Plus /></el-icon>
                Add contact
              </button>
            </div>
          </div>
        </div>

        <div class="field">
          <label class="field__label">小分子亲和力（Affinity）</label>
          <p class="field__hint">
            Boltz-2
            <strong>仅支持小分子配体相对蛋白靶点</strong>
            的亲和力头，不支持蛋白–蛋白。配体建议 ≤56 重原子（硬上限 128）。输出仅供参考，需实验验证。
          </p>
          <el-switch
            v-model="affinityEnabled"
            :disabled="!ligandChainIds.length"
            active-text="开启亲和力预测"
            inactive-text="关闭"
          />
          <p v-if="!ligandChainIds.length" class="field__hint">请先 Add ligand 添加小分子链后再开启。</p>
          <div v-if="affinityEnabled && ligandChainIds.length" class="mt">
            <label class="mini-label">Binder（配体链）</label>
            <el-select v-model="affinityBinder" placeholder="选择配体链" style="width: 160px">
              <el-option v-for="id in ligandChainIds" :key="id" :label="id" :value="id" />
            </el-select>
          </div>
        </div>

        <div class="field">
          <label class="field__label">采样数（Number of Samples）<span class="req">*</span></label>
          <p class="field__hint">
            扩散采样次数（diffusion_samples）。每个样本生成一个构象；增大可提高多样性，但耗时近似线性增加。默认 1。
          </p>
          <el-input-number v-model="boltz.diffusion_samples" :min="1" :max="25" />
        </div>

        <button type="button" class="optional-toggle" @click="showOptional = !showOptional">
          {{ showOptional ? '收起可选参数' : '展开可选参数' }}
          <el-icon><ArrowRight :style="{ transform: showOptional ? 'rotate(90deg)' : '' }" /></el-icon>
        </button>

        <div v-show="showOptional" class="optional">
          <div class="opt-item">
            <h4>循环精炼步数（Number of Recycles）</h4>
            <p>结构预测中的迭代精炼轮数（recycling_steps）。数值越高通常更准，但更慢。推荐 3。</p>
            <el-input-number v-model="boltz.recycling_steps" :min="1" :max="20" />
          </div>

          <div class="opt-item">
            <h4>扩散采样步数（Sampling Steps）</h4>
            <p>
              每个样本的扩散去噪步数（sampling_steps）。步数越多构象更细致，耗时更长。Boltz-2 默认 200。
            </p>
            <el-input-number v-model="boltz.sampling_steps" :min="20" :max="1000" :step="10" />
          </div>

          <div class="opt-item">
            <h4>步长尺度（Step Scale）</h4>
            <p>
              控制扩散采样温度相关的步长。值越小样本多样性越高（推荐 1–2）。留空则使用模型默认（Boltz-2 ≈
              1.5）。
            </p>
            <el-input-number
              v-model="boltz.step_scale"
              :min="0.5"
              :max="5"
              :step="0.1"
              :precision="3"
              controls-position="right"
              placeholder="默认"
            />
            <el-button text type="primary" class="mt-xs" @click="boltz.step_scale = null">
              恢复默认
            </el-button>
          </div>

          <div class="opt-item">
            <h4>随机种子（Seed）</h4>
            <p>固定种子可复现同一结果；留空则每次随机。点击「随机」生成一个种子值。</p>
            <div class="inline">
              <el-input-number
                v-model="boltz.seed"
                :min="0"
                :max="2147483647"
                controls-position="right"
                placeholder="随机"
                style="width: 200px"
              />
              <el-button @click="randomizeSeed">随机</el-button>
              <el-button text @click="clearSeed">清空</el-button>
            </div>
          </div>

          <div class="opt-item">
            <h4>输出格式（Output Format）</h4>
            <p>预测结构文件格式。mmCIF 更适合大复合物；PDB 兼容更多下游工具。</p>
            <el-radio-group v-model="boltz.output_format">
              <el-radio value="mmcif">mmCIF</el-radio>
              <el-radio value="pdb">PDB</el-radio>
            </el-radio-group>
          </div>

          <div class="opt-item">
            <h4>模型版本（Boltz Version）</h4>
            <p>选择 Boltz-1 或 Boltz-2 权重。一般保持 Boltz-2。</p>
            <el-radio-group v-model="boltz.model">
              <el-radio value="boltz2">Boltz-2</el-radio>
              <el-radio value="boltz1">Boltz-1</el-radio>
            </el-radio-group>
          </div>

          <div class="opt-item">
            <h4>实验方法偏置（Method）</h4>
            <p>
              可选。对预测施加实验方法相关偏置（如 x-ray / cryo-em 等，取决于模型支持）。多数情况留空即可。
            </p>
            <el-input v-model="boltz.method" placeholder="可选，留空" clearable />
          </div>

          <div class="opt-item">
            <h4>推理势函数（Use Potentials）</h4>
            <p>
              开启后使用推理时势函数引导（use_potentials），通常能显著提升构象物理质量，代价是更慢。
            </p>
            <el-switch v-model="boltz.use_potentials" active-text="开启" inactive-text="关闭" />
          </div>

          <div class="opt-item">
            <h4>多序列比对 MSA（Use Multiple Sequence Alignment）</h4>
            <p>
              开启后通过 ColabFold/MMseqs2 服务器自动生成 MSA，通常提高精度。关闭可加速，但可能降低准确度（尤其远同源蛋白）。
            </p>
            <el-switch v-model="boltz.use_msa_server" active-text="使用 MSA" inactive-text="禁用 MSA" />
          </div>

          <div v-if="boltz.use_msa_server" class="opt-item">
            <h4>MSA 配对策略（MSA Pairing Strategy）</h4>
            <p>
              多链复合物如何配对同源序列：greedy 更快；complete 更完整但更慢。
            </p>
            <el-radio-group v-model="boltz.msa_pairing_strategy">
              <el-radio value="greedy">greedy</el-radio>
              <el-radio value="complete">complete</el-radio>
            </el-radio-group>
          </div>

          <div class="opt-item">
            <h4>最大 MSA 序列数（Max MSA Sequences）</h4>
            <p>
              MSA 最多保留多少条序列（max_msa_seqs）。更小的值得到更「浅」的 MSA，有时更接近模板/局部构象；默认 8192。
            </p>
            <el-input-number v-model="boltz.max_msa_seqs" :min="64" :max="16384" :step="256" />
          </div>

          <div class="opt-item">
            <h4>MSA 子采样（Subsample MSA）</h4>
            <p>
              开启后从 MSA 中再抽样一部分序列（num_subsampled_msa），可加速并增加构象多样性。
            </p>
            <el-switch v-model="boltz.subsample_msa" active-text="开启" inactive-text="关闭" />
            <div v-if="boltz.subsample_msa" class="mt">
              <span class="sub-label">子采样条数</span>
              <el-input-number v-model="boltz.num_subsampled_msa" :min="16" :max="8192" :step="64" />
            </div>
          </div>

          <div class="opt-item">
            <h4>并行样本数（Max Parallel Samples）</h4>
            <p>
              一次并行预测多少个扩散样本。受显存限制；默认 5。采样数很大时可适当调低避免 OOM。
            </p>
            <el-input-number v-model="boltz.max_parallel_samples" :min="1" :max="25" />
          </div>

          <div class="opt-item">
            <h4>额外输出</h4>
            <p>按需写出中间矩阵/嵌入；文件更大，一般分析可关闭。</p>
            <div class="checks">
              <el-checkbox v-model="boltz.write_full_pae">写出完整 PAE（write_full_pae）</el-checkbox>
              <el-checkbox v-model="boltz.write_full_pde">写出完整 PDE（write_full_pde）</el-checkbox>
              <el-checkbox v-model="boltz.write_embeddings">写出嵌入 embeddings</el-checkbox>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="optional">
          <div class="opt-item">
            <h4>ESMFold2 · loops</h4>
            <p>循环精炼轮数。越大越慢，可能略提升质量。</p>
            <el-input-number v-model="esmLoops" :min="1" :max="8" />
          </div>
          <div class="opt-item">
            <h4>ESMFold2 · sampling steps</h4>
            <p>采样步数。</p>
            <el-input-number v-model="esmSteps" :min="50" :max="500" :step="50" />
          </div>
          <div class="opt-item">
            <h4>ESMFold2 · diffusion samples</h4>
            <p>生成构象数。</p>
            <el-input-number v-model="esmSamples" :min="1" :max="5" />
          </div>
        </div>
      </template>

      <div class="actions">
        <el-button type="primary" size="large" :loading="submitting" @click="submitSingle">
          提交预测
        </el-button>
        <p v-if="!chainEntities.some((e) => (e.entity === 'ligand' ? e.smiles || e.ccd : e.sequence.trim()))" class="actions__warn">
          请先填写非空序列。
        </p>
      </div>
    </div>

    <!-- 批量 -->
    <div v-show="submitTab === 'batch'" class="boltz-form__body">
      <div class="field">
        <label class="field__label">批次名称</label>
        <el-input v-model="batchName" placeholder="可选" />
      </div>
      <div class="field">
        <label class="field__label">靶点名称</label>
        <el-input v-model="targetName" />
      </div>
      <div class="field">
        <label class="field__label">抗原序列</label>
        <el-input v-model="targetSeq" type="textarea" :rows="4" />
      </div>
      <div class="inline">
        <div class="field">
          <label class="field__label">抗原链 ID</label>
          <el-input v-model="targetChainId" style="width: 100px" />
        </div>
        <div class="field">
          <label class="field__label">重链链 ID</label>
          <el-input v-model="heavyChainId" style="width: 100px" />
        </div>
      </div>
      <div class="field">
        <label class="field__label">预测引擎</label>
        <el-radio-group v-model="foldEngine">
          <el-radio-button value="boltz2">Boltz-2</el-radio-button>
          <el-radio-button value="esmfold2">ESMFold2</el-radio-button>
        </el-radio-group>
      </div>
      <div v-if="foldEngine === 'boltz2'" class="field">
        <label class="field__label">采样数 / MSA</label>
        <p class="field__hint">批量任务将复用上方 Boltz 可选参数（采样数、循环步、MSA 等）。</p>
        <div class="inline">
          <el-input-number v-model="boltz.diffusion_samples" :min="1" :max="25" />
          <el-switch v-model="boltz.use_msa_server" active-text="MSA" inactive-text="无 MSA" />
        </div>
      </div>
      <div class="field">
        <label class="field__label">重链列表</label>
        <el-radio-group v-model="heavyTab" size="small">
          <el-radio-button value="csv">CSV</el-radio-button>
          <el-radio-button value="fasta">FASTA</el-radio-button>
        </el-radio-group>
        <el-input
          v-if="heavyTab === 'csv'"
          v-model="heavyCsvInput"
          type="textarea"
          :rows="6"
          placeholder="vhh_id,sequence"
          class="mt"
        />
        <el-input
          v-else
          v-model="heavyFastaInput"
          type="textarea"
          :rows="6"
          placeholder=">VHH_001&#10;QVQL..."
          class="mt"
        />
        <el-upload
          class="mt"
          :auto-upload="false"
          :show-file-list="false"
          accept=".csv,.txt,.fasta,.fa,.xlsx,.xlsm"
          @change="onHeavyFileChange"
        >
          <el-button>导入 CSV / Excel / FASTA</el-button>
        </el-upload>
        <p v-if="heavyFileHint" class="field__hint">{{ heavyFileHint }}</p>
        <p v-if="heavyPreview.length" class="field__hint">已识别 {{ heavyPreview.length }} 条重链</p>
      </div>
      <div class="actions">
        <el-button type="primary" size="large" :loading="submitting" @click="submitBatch">
          开始批量预测
        </el-button>
      </div>
    </div>

    <p v-if="lastStatus" class="boltz-form__status">{{ lastStatus }}</p>
  </div>
</template>

<style scoped lang="scss">
.boltz-form {
  max-width: 760px;
}

.boltz-form__back {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 1.25rem;
  padding: 0;
  border: none;
  background: transparent;
  color: #6b7280;
  font-size: 0.86rem;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    color: #111827;
  }
}

.boltz-form__hero {
  margin-bottom: 1.5rem;
}

.boltz-form__hero-top {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;

  h1 {
    margin: 0;
    font-size: 1.85rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #111827;
  }
}

.boltz-form__badge {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #374151;
  background: #f3f4f6;
}

.boltz-form__meta {
  font-size: 0.78rem;
  color: #9ca3af;
  font-weight: 600;
}

.boltz-form__desc {
  margin: 0.55rem 0 0;
  font-size: 0.92rem;
  line-height: 1.6;
  color: #6b7280;
}

.boltz-form__tabs {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 1.35rem;
  padding: 0.25rem;
  background: #f3f4f6;
  border-radius: 10px;
}

.boltz-form__tab {
  flex: 1;
  border: none;
  background: transparent;
  color: #6b7280;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;

  &.active {
    background: #fff;
    color: #111827;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  }
}

.field {
  margin-bottom: 1.35rem;
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
}

.mt {
  margin-top: 0.55rem;
  width: 100%;
}

.mt-xs {
  margin-top: 0.35rem;
}

.optional-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0.25rem 0 1rem;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 0.88rem;
  font-weight: 700;
  color: #111827;
  cursor: pointer;
}

.optional {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 1.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  overflow: hidden;
}

.opt-item {
  padding: 1.1rem 1.2rem;
  border-bottom: 1px solid #f3f4f6;
  background: #fff;

  &:last-child {
    border-bottom: none;
  }

  h4 {
    margin: 0 0 0.35rem;
    font-size: 0.92rem;
    font-weight: 700;
    color: #111827;
  }

  p {
    margin: 0 0 0.75rem;
    font-size: 0.8rem;
    line-height: 1.55;
    color: #6b7280;
  }
}

.inline {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.checks {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.sub-label {
  display: inline-block;
  margin-right: 0.65rem;
  font-size: 0.8rem;
  color: #6b7280;
}

.actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding-top: 0.5rem;
}

.actions__warn {
  margin: 0;
  font-size: 0.8rem;
  color: #9ca3af;
}

.restraint-box {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.restraint-card {
  padding: 0.85rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fafafa;
}

.restraint-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.55rem;

  strong {
    font-size: 0.88rem;
    color: #111827;
  }
}

.mini-label {
  display: block;
  margin: 0.45rem 0 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
}

.add-chain-mini {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4rem 0.75rem;
  border: 1px dashed #d1d5db;
  border-radius: 999px;
  background: #fff;
  font-size: 0.8rem;
  font-weight: 700;
  color: #111827;
  cursor: pointer;

  &:hover {
    border-color: #111827;
  }
}

.boltz-form__status {
  margin: 1.25rem 0 0;
  padding: 0.75rem 0.9rem;
  border-radius: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  color: #374151;
  font-size: 0.84rem;
}
</style>
