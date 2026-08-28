<script setup lang="ts">
import { computed, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'

export type ChainEntityType = 'protein' | 'dna' | 'rna' | 'ligand'

export interface ChainModification {
  position: number
  ccd: string
}

export interface ChainEntity {
  key: string
  entity: ChainEntityType
  copies: number
  ids: string[]
  sequence: string
  ligandMode: 'smiles' | 'ccd'
  smiles: string
  ccd: string
  cyclic: boolean
  modifications: ChainModification[]
  plainView: boolean
}

const props = defineProps<{
  modelValue: ChainEntity[]
  /** ESMFold2 时隐藏配体类型 */
  allowLigand?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ChainEntity[]]
}>()

const entities = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const typeOptions = computed(() => {
  const base: Array<{ value: ChainEntityType; label: string }> = [
    { value: 'protein', label: 'Protein' },
    { value: 'dna', label: 'DNA' },
    { value: 'rna', label: 'RNA' },
  ]
  if (props.allowLigand !== false) {
    base.push({ value: 'ligand', label: 'Ligand' })
  }
  return base
})

function uid() {
  return `c_${Math.random().toString(36).slice(2, 9)}`
}

function nextIds(startIndex: number, count: number): string[] {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  const ids: string[] = []
  for (let i = 0; i < count; i++) {
    const n = startIndex + i
    if (n < 26) ids.push(letters[n]!)
    else ids.push(`X${n - 25}`)
  }
  return ids
}

function reassignAll(list: ChainEntity[]) {
  let idx = 0
  for (const e of list) {
    const copies = Math.max(1, Math.min(12, e.copies || 1))
    e.copies = copies
    e.ids = nextIds(idx, copies)
    idx += copies
  }
}

function patch(i: number, partial: Partial<ChainEntity>) {
  const next = entities.value.map((e, j) => (j === i ? { ...e, ...partial } : { ...e }))
  if (partial.copies != null || partial.entity != null) reassignAll(next)
  entities.value = next
}

function addChain(entity: ChainEntityType = 'protein') {
  const next = [
    ...entities.value.map((e) => ({ ...e })),
    {
      key: uid(),
      entity,
      copies: 1,
      ids: ['A'],
      sequence: '',
      ligandMode: 'smiles' as const,
      smiles: '',
      ccd: '',
      cyclic: false,
      modifications: [],
      plainView: false,
    },
  ]
  reassignAll(next)
  entities.value = next
}

function removeChain(i: number) {
  if (entities.value.length <= 1) return
  const next = entities.value.filter((_, j) => j !== i).map((e) => ({ ...e }))
  reassignAll(next)
  entities.value = next
}

function bumpCopies(i: number, delta: number) {
  const cur = entities.value[i]
  if (!cur) return
  patch(i, { copies: Math.max(1, Math.min(12, cur.copies + delta)) })
}

function addModification(i: number) {
  const cur = entities.value[i]
  if (!cur) return
  patch(i, {
    modifications: [...cur.modifications, { position: 1, ccd: '' }],
  })
}

function removeModification(i: number, mi: number) {
  const cur = entities.value[i]
  if (!cur) return
  patch(i, {
    modifications: cur.modifications.filter((_, j) => j !== mi),
  })
}

function updateMod(i: number, mi: number, partial: Partial<ChainModification>) {
  const cur = entities.value[i]
  if (!cur) return
  patch(i, {
    modifications: cur.modifications.map((m, j) => (j === mi ? { ...m, ...partial } : m)),
  })
}

function placeholder(entity: ChainEntityType) {
  if (entity === 'ligand') return 'Paste SMILES or switch to CCD…'
  if (entity === 'dna') return 'Paste or type DNA sequence (ACGT)…'
  if (entity === 'rna') return 'Paste or type RNA sequence (ACGU)…'
  return 'Paste or type your protein sequence here…'
}

function chainLabel(ids: string[]) {
  if (ids.length === 1) return `Chain ${ids[0]}`
  return `Chains ${ids.join(', ')}`
}

watch(
  () => props.allowLigand,
  (allow) => {
    if (allow === false && entities.value.some((e) => e.entity === 'ligand')) {
      const next = entities.value.map((e) =>
        e.entity === 'ligand' ? { ...e, entity: 'protein' as const, smiles: '', ccd: '' } : { ...e },
      )
      reassignAll(next)
      entities.value = next
    }
  },
)

defineExpose({ addChain, reassignAll })
</script>

<template>
  <div class="chain-builder">
    <div v-for="(ent, i) in entities" :key="ent.key" class="chain-card">
      <div class="chain-card__grip" aria-hidden="true">⋮⋮</div>
      <div class="chain-card__main">
        <div class="chain-card__head">
          <el-select
            :model-value="ent.entity"
            style="width: 130px"
            @update:model-value="(v: ChainEntityType) => patch(i, { entity: v })"
          >
            <el-option
              v-for="opt in typeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>

          <div class="copies">
            <span>Copies</span>
            <button type="button" class="copies__btn" @click="bumpCopies(i, -1)">−</button>
            <input
              class="copies__input"
              type="number"
              min="1"
              max="12"
              :value="ent.copies"
              @change="
                patch(i, {
                  copies: Math.max(1, Math.min(12, Number(($event.target as HTMLInputElement).value) || 1)),
                })
              "
            />
            <button type="button" class="copies__btn" @click="bumpCopies(i, 1)">+</button>
          </div>

          <div class="chain-card__spacer" />

          <button type="button" class="text-btn" @click="patch(i, { plainView: !ent.plainView })">
            {{ ent.plainView ? 'View Card' : 'View Plain Text' }}
          </button>
          <span class="chain-pill">{{ chainLabel(ent.ids) }}</span>
          <button
            type="button"
            class="icon-btn"
            :disabled="entities.length <= 1"
            title="删除"
            @click="removeChain(i)"
          >
            <el-icon><Delete /></el-icon>
          </button>
        </div>

        <template v-if="ent.entity === 'ligand'">
          <div class="ligand-mode">
            <el-radio-group
              :model-value="ent.ligandMode"
              size="small"
              @update:model-value="(v) => patch(i, { ligandMode: (v as 'smiles' | 'ccd') || 'smiles' })"
            >
              <el-radio-button value="smiles">SMILES</el-radio-button>
              <el-radio-button value="ccd">CCD</el-radio-button>
            </el-radio-group>
          </div>
          <el-input
            v-if="ent.ligandMode === 'smiles'"
            :model-value="ent.smiles"
            type="textarea"
            :rows="ent.plainView ? 3 : 4"
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
            @update:model-value="(v: string) => patch(i, { smiles: v })"
          />
          <el-input
            v-else
            :model-value="ent.ccd"
            placeholder="e.g. ATP / SAH"
            @update:model-value="(v: string) => patch(i, { ccd: v })"
          />
        </template>
        <el-input
          v-else
          :model-value="ent.sequence"
          type="textarea"
          :rows="ent.plainView ? 3 : 5"
          :placeholder="placeholder(ent.entity)"
          @update:model-value="(v: string) => patch(i, { sequence: v })"
        />

        <div v-if="ent.entity !== 'ligand'" class="chain-card__foot">
          <el-checkbox
            :model-value="ent.cyclic"
            @update:model-value="(v) => patch(i, { cyclic: Boolean(v) })"
          >
            Cyclic
          </el-checkbox>
          <button type="button" class="mod-btn" @click="addModification(i)">
            <el-icon><Plus /></el-icon>
            Add modification
          </button>
        </div>

        <div v-if="ent.modifications.length" class="mods">
          <div v-for="(mod, mi) in ent.modifications" :key="mi" class="mods__row">
            <span>位置</span>
            <el-input-number
              :model-value="mod.position"
              :min="1"
              size="small"
              @update:model-value="(v: number | undefined) => updateMod(i, mi, { position: v || 1 })"
            />
            <span>CCD</span>
            <el-input
              :model-value="mod.ccd"
              size="small"
              placeholder="修饰残基 CCD"
              style="width: 140px"
              @update:model-value="(v: string) => updateMod(i, mi, { ccd: v })"
            />
            <button type="button" class="icon-btn" @click="removeModification(i, mi)">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="chain-builder__actions">
      <button type="button" class="add-chain" @click="addChain('protein')">
        <el-icon><Plus /></el-icon>
        Add chain
      </button>
      <button
        v-if="allowLigand !== false"
        type="button"
        class="add-chain add-chain--ghost"
        @click="addChain('ligand')"
      >
        <el-icon><Plus /></el-icon>
        Add ligand
      </button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.chain-builder {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.chain-card {
  display: flex;
  gap: 0.45rem;
  align-items: stretch;
}

.chain-card__grip {
  width: 18px;
  color: #d1d5db;
  font-size: 0.7rem;
  letter-spacing: -2px;
  padding-top: 1.1rem;
  user-select: none;
}

.chain-card__main {
  flex: 1;
  min-width: 0;
  padding: 0.85rem 1rem 0.9rem;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
}

.chain-card__head {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-bottom: 0.65rem;
}

.chain-card__spacer {
  flex: 1;
}

.copies {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: #6b7280;
}

.copies__btn {
  width: 26px;
  height: 26px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: #111827;

  &:hover {
    background: #f3f4f6;
  }
}

.copies__input {
  width: 42px;
  height: 26px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  text-align: center;
  font-size: 0.84rem;
  font-weight: 700;
}

.chain-pill {
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #374151;
  background: #f3f4f6;
}

.text-btn,
.mod-btn {
  border: none;
  background: transparent;
  color: #0f766e;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
}

.mod-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}

.icon-btn {
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  display: inline-flex;
  padding: 0.2rem;

  &:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  &:hover:not(:disabled) {
    color: #ef4444;
  }
}

.ligand-mode {
  margin-bottom: 0.45rem;
}

.chain-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 0.65rem;
}

.mods {
  margin-top: 0.55rem;
  padding-top: 0.55rem;
  border-top: 1px dashed #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.mods__row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
  font-size: 0.78rem;
  color: #6b7280;
}

.chain-builder__actions {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.add-chain {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.55rem 0.9rem;
  border: 1px dashed #d1d5db;
  border-radius: 999px;
  background: #fff;
  color: #111827;
  font-size: 0.84rem;
  font-weight: 700;
  cursor: pointer;

  &:hover {
    border-color: #111827;
  }

  &--ghost {
    color: #6b7280;
  }
}
</style>
