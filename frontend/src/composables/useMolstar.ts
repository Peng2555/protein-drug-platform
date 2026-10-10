import { QualityAssessmentProvider } from 'molstar/lib/extensions/model-archive/quality-assessment/prop'
import { Viewer } from 'molstar/lib/apps/viewer/app'
import { Bond, QueryContext, StructureElement, StructureProperties, StructureSelection, Unit } from 'molstar/lib/mol-model/structure'
import { MinimizeRmsd } from 'molstar/lib/mol-math/linear-algebra/3d/minimize-rmsd'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import { MolScriptBuilder as MS } from 'molstar/lib/mol-script/language/builder'
import { compile } from 'molstar/lib/mol-script/runtime/query/compiler'
import { StateTransforms } from 'molstar/lib/mol-plugin-state/transforms'
import { PluginStateObject } from 'molstar/lib/mol-plugin-state/objects'
import { StructureFocusRepresentation } from 'molstar/lib/mol-plugin/behavior/dynamic/selection/structure-focus-representation'
import { PresetStructureRepresentations } from 'molstar/lib/mol-plugin-state/builder/structure/representation-preset'
import { ColorThemeCategory } from 'molstar/lib/mol-theme/color/categories'
import type { ColorTheme } from 'molstar/lib/mol-theme/color'
import { Color } from 'molstar/lib/mol-util/color'
import { ParamDefinition as PD } from 'molstar/lib/mol-util/param-definition'
import type { PluginUIContext } from 'molstar/lib/mol-plugin-ui/context'
import type { InterfaceChainMeta, SelectedResidue, ViewerColorMode } from '@/types/structure'

export interface MolstarViewer {
  plugin: PluginUIContext
  loadStructureFromData: Viewer['loadStructureFromData']
  structureInteractivity: Viewer['structureInteractivity']
  handleResize: () => void
  dispose: () => void
  subscribe: Viewer['subscribe']
}

const PLDDT_THEME_NAME = 'boltz-plddt'
const PLDDT_BUILTIN_THEME = 'plddt-confidence'

const PLDDT_COLORS = {
  default: Color(0x8b949e),
  high: Color(0x0053d6),
  good: Color(0x00c1f2),
  low: Color(0xfffd00),
  poor: Color(0xff7d00),
} as const

/** Boltz stores pLDDT as 0–1 in mmCIF B-factors; AlphaFold uses 0–100. */
function normalizePlddtScore(raw: number): number {
  let v = raw
  if (Number.isNaN(v) || v < 0) return -1
  if (v <= 1.5) v *= 100
  return v
}

function plddtScoreToColor(score: number) {
  const v = normalizePlddtScore(score)
  if (v < 0) return PLDDT_COLORS.default
  if (v > 90) return PLDDT_COLORS.high
  if (v > 70) return PLDDT_COLORS.good
  if (v > 50) return PLDDT_COLORS.low
  return PLDDT_COLORS.poor
}

const BoltzPlddtColorThemeParams = {}

function createBoltzPlddtColorTheme(ctx: { structure?: { root: unknown } }) {
  const color = (location: unknown) => {
    if (StructureElement.Location.is(location)) {
      const { unit, element } = location
      if (!Unit.isAtomic(unit)) return PLDDT_COLORS.default
      const score = unit.model.atomicConformation.B_iso_or_equiv.value(element)
      return plddtScoreToColor(score)
    }
    if (Bond.isLocation(location)) {
      const unit = location.aUnit
      const element = location.aUnit.elements[location.aIndex]
      if (!Unit.isAtomic(unit)) return PLDDT_COLORS.default
      const score = unit.model.atomicConformation.B_iso_or_equiv.value(element)
      return plddtScoreToColor(score)
    }
    return PLDDT_COLORS.default
  }
  void ctx
  return {
    factory: createBoltzPlddtColorTheme,
    granularity: 'group' as const,
    preferSmoothing: true,
    color,
    props: BoltzPlddtColorThemeParams,
    description: 'AlphaFold/Boltz pLDDT from mmCIF B-factors (supports 0–100 and 0–1).',
  }
}

const BoltzPlddtColorThemeProvider = {
  name: PLDDT_THEME_NAME,
  label: 'pLDDT',
  category: ColorThemeCategory.Validation,
  factory: createBoltzPlddtColorTheme,
  getParams: () => BoltzPlddtColorThemeParams,
  defaultValues: PD.getDefaultValues(BoltzPlddtColorThemeParams),
  isApplicable: (ctx: { structure?: { models: Array<{ atomicConformation: { B_iso_or_equiv: { isDefined: boolean } } }> } }) =>
    !!ctx.structure?.models.some((m) => m.atomicConformation.B_iso_or_equiv.isDefined),
} as ColorTheme.Provider

function registerBoltzPlddtTheme(plugin: PluginUIContext): void {
  const registry = plugin.representation.structure.themes.colorThemeRegistry
  if (!registry.has(BoltzPlddtColorThemeProvider)) {
    registry.add(BoltzPlddtColorThemeProvider)
  }
}

function resolvePlddtThemeName(plugin: PluginUIContext): string {
  const provider = plugin.representation.structure.themes.colorThemeRegistry.get(PLDDT_BUILTIN_THEME)
  if (provider.name === PLDDT_BUILTIN_THEME) return PLDDT_BUILTIN_THEME
  registerBoltzPlddtTheme(plugin)
  return PLDDT_THEME_NAME
}

async function ensurePlddtThemeDependencies(plugin: PluginUIContext): Promise<void> {
  for (const s of plugin.managers.structure.hierarchy.current.structures) {
    const structure = s.cell.obj?.data
    if (!structure) continue
    for (const model of structure.models) {
      try {
        await QualityAssessmentProvider.attach(plugin as never, model, undefined, true)
      } catch {
        /* B-factor fallback does not require QA props */
      }
    }
  }
}

type ThemeUpdateParams = {
  color: string
  colorParams?: Record<string, unknown>
}

async function updateAllRepresentationThemes(
  plugin: PluginUIContext,
  params: ThemeUpdateParams,
): Promise<void> {
  await plugin.dataTransaction(async () => {
    for (const s of plugin.managers.structure.hierarchy.current.structures) {
      await plugin.managers.structure.component.updateRepresentationsTheme(
        s.components,
        params as never,
      )
    }
  })
  plugin.canvas3d?.requestDraw()
}

const VIEWER_OPTIONS = {
  layoutIsExpanded: false,
  layoutShowControls: false,
  layoutShowRemoteState: false,
  layoutShowSequence: false,
  layoutShowLog: false,
  layoutShowLeftPanel: false,
  collapseLeftPanel: true,
  collapseRightPanel: true,
  viewportShowExpand: false,
  viewportShowSettings: false,
  viewportShowSelectionMode: false,
  viewportShowAnimation: false,
  viewportShowTrajectoryControls: false,
  viewportShowScreenshotControls: true,
  viewportShowReset: true,
  viewportShowControls: true,
  viewportShowToggleFullscreen: false,
  viewportBackgroundColor: '0xf1f5f9',
  illumination: false,
  viewportFocusBehavior: 'default',
} as const

export async function createMolstarViewer(
  container: HTMLElement,
  options: Record<string, unknown> = {},
): Promise<MolstarViewer> {
  container.innerHTML = ''
  container.style.position = 'relative'
  container.style.width = '100%'
  container.style.height = '100%'
  return Viewer.create(container, { ...VIEWER_OPTIONS, ...options }).then(async (viewer) => {
    registerBoltzPlddtTheme(viewer.plugin)
    try {
      await viewer.plugin.state.updateBehavior(StructureFocusRepresentation, (params) => {
        params.components = ['target', 'surroundings', 'interactions']
        params.ignoreHydrogens = true
        params.expandRadius = 5
      })
    } catch {
      /* 部分 Mol* 版本无此 behavior */
    }
    return viewer as MolstarViewer
  })
}

export function destroyMolstarViewer(viewer: MolstarViewer | null, container?: HTMLElement | null): void {
  try {
    viewer?.dispose()
  } catch {
    /* ignore dispose races */
  }
  if (container) container.innerHTML = ''
}

export function resizeMolstarViewer(viewer: MolstarViewer | null): void {
  viewer?.handleResize()
}

export async function loadMolstarCif(viewer: MolstarViewer, cifText: string): Promise<void> {
  await loadMolstarStructure(viewer, cifText, 'mmcif')
}

export function detectStructureFormat(text: string): 'mmcif' | 'pdb' {
  const head = text.slice(0, 4096).trimStart().toLowerCase()
  if (head.startsWith('data_') || head.includes('_atom_site.') || head.includes('loop_')) {
    return 'mmcif'
  }
  return 'pdb'
}

export async function loadMolstarStructure(
  viewer: MolstarViewer,
  text: string,
  format?: 'mmcif' | 'pdb',
  options?: {
    resetCamera?: boolean
    dataLabel?: string
    preset?: MolstarReprKind
  },
): Promise<void> {
  const fmt = format ?? detectStructureFormat(text)
  const plugin = viewer.plugin
  await plugin.initialized
  const data = await plugin.builders.data.rawData({
    data: text,
    label: options?.dataLabel ?? 'structure',
  })
  const trajectory = await plugin.builders.structure.parseTrajectory(data, fmt)
  const model = await plugin.builders.structure.createModel(trajectory)
  await plugin.builders.structure.createStructure(model)
  const structures = plugin.managers.structure.hierarchy.current.structures.slice(-1)
  const preset = options?.preset ?? 'polymer-and-ligand'
  await plugin.managers.structure.component.applyPreset(
    structures,
    PresetStructureRepresentations[preset],
    { ignoreHydrogens: true, quality: 'auto' } as never,
  )
  if (options?.resetCamera !== false) {
    plugin.canvas3d?.requestCameraReset()
  }
}

export async function clearMolstarPlugin(viewer: MolstarViewer): Promise<void> {
  await viewer.plugin.clear()
}

export type MolstarReprKind = 'molecular-surface' | 'polymer-cartoon' | 'polymer-and-ligand'

/** 切换 cartoon / 分子表面。表面计算较慢，调用方应避免在每次着色时重复套用。 */
export async function applyMolstarStructurePreset(
  viewer: MolstarViewer,
  kind: MolstarReprKind,
): Promise<void> {
  const { plugin } = viewer
  const structures = plugin.managers.structure.hierarchy.current.structures
  if (!structures.length) return
  const provider = PresetStructureRepresentations[kind]
  await plugin.managers.structure.component.applyPreset(structures, provider, {
    quality: kind === 'molecular-surface' ? 'high' : 'auto',
    ignoreHydrogens: true,
    ignoreLight: false,
  } as never)
  plugin.canvas3d?.requestDraw()
}

export async function applyMolstarColorMode(viewer: MolstarViewer, mode: ViewerColorMode): Promise<void> {
  const { plugin } = viewer
  const structures = plugin.managers.structure.hierarchy.current.structures
  if (!structures.length) return

  if (mode === 'plddt') {
    registerBoltzPlddtTheme(plugin)
    await ensurePlddtThemeDependencies(plugin)
    const themeName = resolvePlddtThemeName(plugin)
    await updateAllRepresentationThemes(plugin, {
      color: themeName,
    } as ThemeUpdateParams)
    return
  }

  await updateAllRepresentationThemes(plugin, { color: 'chain-id' })
}

const HYDRO_PATCH_THEME_NAME = 'boltz-hydro-patch'

type HydroPatchThemeState = {
  colorByKey: Map<string, number>
  patchByKey: Map<string, string>
  focusPatchId: string | null
}

const hydroPatchThemeState: HydroPatchThemeState = {
  colorByKey: new Map(),
  patchByKey: new Map(),
  focusPatchId: null,
}

const HYDRO_BASE = Color(0xe8edf3)
const HYDRO_DIM = Color(0xcbd5e1)

function hydroLocationKey(location: StructureElement.Location): string | null {
  const chain =
    StructureProperties.chain.auth_asym_id(location) ||
    StructureProperties.chain.label_asym_id(location)
  const seq =
    StructureProperties.residue.auth_seq_id(location) ??
    StructureProperties.residue.label_seq_id(location)
  if (!chain || seq == null || Number.isNaN(Number(seq))) return null
  return `${chain}:${Number(seq)}`
}

function hydroColorForKey(key: string | null): Color {
  if (!key) return HYDRO_BASE
  const patchId = hydroPatchThemeState.patchByKey.get(key)
  const rgb = hydroPatchThemeState.colorByKey.get(key)
  if (!patchId || rgb == null) return HYDRO_BASE
  if (hydroPatchThemeState.focusPatchId && hydroPatchThemeState.focusPatchId !== patchId) {
    return HYDRO_DIM
  }
  return Color(rgb)
}

const HydroPatchColorThemeParams = {}

function createHydroPatchColorTheme(ctx: { structure?: { root: unknown } }) {
  const color = (location: unknown) => {
    if (StructureElement.Location.is(location) && Unit.isAtomic(location.unit)) {
      return hydroColorForKey(hydroLocationKey(location))
    }
    return HYDRO_BASE
  }
  void ctx
  return {
    factory: createHydroPatchColorTheme,
    granularity: 'group' as const,
    preferSmoothing: true,
    color,
    props: HydroPatchColorThemeParams,
    description: 'Engineerable hydrophobic patches (surface SAP ≥ 0.5).',
  }
}

const HydroPatchColorThemeProvider = {
  name: HYDRO_PATCH_THEME_NAME,
  label: 'Hydrophobic patch',
  category: ColorThemeCategory.Validation,
  factory: createHydroPatchColorTheme,
  getParams: () => HydroPatchColorThemeParams,
  defaultValues: PD.getDefaultValues(HydroPatchColorThemeParams),
  isApplicable: () => true,
} as ColorTheme.Provider

function registerHydroPatchTheme(plugin: PluginUIContext): void {
  const registry = plugin.representation.structure.themes.colorThemeRegistry
  if (!registry.has(HydroPatchColorThemeProvider)) {
    registry.add(HydroPatchColorThemeProvider)
  }
}

export type HydroPatchColorInput = {
  residueColors: Map<string, string>
  residuePatch: Map<string, string>
  focusPatchId?: string | null
}

export async function applyMolstarHydroPatchTheme(
  viewer: MolstarViewer,
  state: HydroPatchColorInput,
): Promise<void> {
  hydroPatchThemeState.colorByKey = new Map(
    [...state.residueColors.entries()].map(([k, hex]) => [k, parseInt(hex.replace('#', ''), 16)]),
  )
  hydroPatchThemeState.patchByKey = new Map(state.residuePatch)
  hydroPatchThemeState.focusPatchId = state.focusPatchId ?? null
  registerHydroPatchTheme(viewer.plugin)
  await updateAllRepresentationThemes(viewer.plugin, { color: HYDRO_PATCH_THEME_NAME })
}

export function syncMolstarSelection(viewer: MolstarViewer, selected: SelectedResidue[]): void {
  if (!selected.length) {
    viewer.structureInteractivity({ action: 'select' })
    return
  }
  viewer.structureInteractivity({
    action: 'select',
    elements: {
      items: selected.map((r) => ({
        auth_asym_id: r.chainId,
        auth_seq_id: r.resi,
      })),
    },
  })
}

export function bindMolstarResiduePick(
  viewer: MolstarViewer,
  onPick: (chainId: string, resi: number, event: Pick<MouseEvent, 'shiftKey' | 'ctrlKey' | 'metaKey'>) => void,
): { unsubscribe: () => void } {
  return viewer.subscribe(
    viewer.plugin.behaviors.interaction.click,
    ({ current, button, modifiers }: { current: { loci: unknown }; button: number; modifiers: { shift: boolean; control: boolean; meta: boolean } }) => {
    if (button !== 0) return
    const loci = current.loci
    if (!StructureElement.Loci.is(loci)) return
    const loc = StructureElement.Loci.getFirstLocation(loci)
    if (!loc) return
    const chainId =
      StructureProperties.chain.auth_asym_id(loc) ||
      StructureProperties.chain.label_asym_id(loc)
    const resi =
      StructureProperties.residue.auth_seq_id(loc) ??
      StructureProperties.residue.label_seq_id(loc)
    if (!chainId || resi == null || Number.isNaN(Number(resi))) return
    onPick(String(chainId), Number(resi), {
      shiftKey: modifiers.shift,
      ctrlKey: modifiers.control,
      metaKey: modifiers.meta,
    })
  })
}

export function hexColorToInt(hex: string | undefined | null): number {
  if (!hex) return 0x8b949e
  return parseInt(hex.replace('#', ''), 16)
}

export function highlightMolstarResidues(
  viewer: MolstarViewer,
  residues: Array<{ chain_id: string; seq_num: number }>,
  action: 'select' | 'highlight' = 'highlight',
): void {
  if (!residues.length) {
    viewer.structureInteractivity({ action })
    return
  }
  viewer.structureInteractivity({
    action,
    elements: {
      items: residues.map((r) => ({
        auth_asym_id: r.chain_id,
        auth_seq_id: r.seq_num,
      })),
    },
  })
}

export function focusMolstarResidues(
  viewer: MolstarViewer,
  residues: Array<{ chain_id: string; seq_num: number }>,
): void {
  const plugin = viewer.plugin
  if (!residues.length) {
    plugin.managers.structure.focus.clear()
    plugin.canvas3d?.requestCameraReset()
    return
  }
  const schema = {
    items: residues.map((r) => ({
      auth_asym_id: r.chain_id,
      auth_seq_id: r.seq_num,
    })),
  }
  const structures = plugin.state.data.selectQ((Q) => Q.rootsOfType(PluginStateObject.Molecule.Structure))
  for (const s of structures) {
    const structure = s.obj?.data
    if (!structure) continue
    const loci = StructureElement.Loci.fromSchema(structure, schema)
    if (StructureElement.Loci.isEmpty(loci)) continue
    plugin.managers.structure.focus.setFromLoci(loci)
    plugin.managers.camera.focusLoci(loci)
    return
  }
}

export function focusMolstarPoint(
  viewer: MolstarViewer,
  mid: { x: number; y: number; z: number },
): void {
  viewer.plugin.managers.camera.focusSphere(
    { center: Vec3.create(mid.x, mid.y, mid.z), radius: 8 },
    { durationMs: 250 },
  )
}

/** Optional custom chain palette (falls back to Mol* chain-id colors). */
export async function applyMolstarChainPalette(
  viewer: MolstarViewer,
  chains: InterfaceChainMeta[],
): Promise<void> {
  if (!chains.length) return
  await applyMolstarColorMode(viewer, 'chain')
}

const MUTATION_THEME_NAME = 'boltz-mutation-sites'

const mutationThemeState = {
  keys: new Set<string>(),
}

const MUTATION_BASE = Color(0xcbd5e1)
const MUTATION_HIT = Color(0xe11d48)

function mutationLocationKey(location: StructureElement.Location): string | null {
  const chain =
    StructureProperties.chain.auth_asym_id(location) ||
    StructureProperties.chain.label_asym_id(location)
  const seq =
    StructureProperties.residue.auth_seq_id(location) ??
    StructureProperties.residue.label_seq_id(location)
  if (!chain || seq == null || Number.isNaN(Number(seq))) return null
  return `${chain}:${Number(seq)}`
}

const MutationColorThemeParams = {}

function createMutationColorTheme(ctx: { structure?: { root: unknown } }) {
  const color = (location: unknown) => {
    if (StructureElement.Location.is(location) && Unit.isAtomic(location.unit)) {
      const key = mutationLocationKey(location)
      if (key && mutationThemeState.keys.has(key)) return MUTATION_HIT
    }
    return MUTATION_BASE
  }
  void ctx
  return {
    factory: createMutationColorTheme,
    granularity: 'group' as const,
    preferSmoothing: true,
    color,
    props: {},
    description: 'Highlight antibody mutation sites.',
  }
}

const MutationColorThemeProvider = {
  name: MUTATION_THEME_NAME,
  label: 'Mutations',
  category: ColorThemeCategory.Validation,
  factory: createMutationColorTheme,
  getParams: () => MutationColorThemeParams,
  defaultValues: PD.getDefaultValues(MutationColorThemeParams),
  isApplicable: () => true,
} as ColorTheme.Provider

export async function applyMolstarMutationTheme(
  viewer: MolstarViewer,
  residueKeys: Iterable<string>,
): Promise<void> {
  mutationThemeState.keys = new Set(residueKeys)
  const registry = viewer.plugin.representation.structure.themes.colorThemeRegistry
  if (!registry.has(MutationColorThemeProvider)) {
    registry.add(MutationColorThemeProvider)
  }
  await updateAllRepresentationThemes(viewer.plugin, { color: MUTATION_THEME_NAME })
}

function caQuery() {
  return compile(MS.struct.generator.atomGroups({
    'atom-test': MS.core.rel.eq([MS.struct.atomProperty.macromolecular.label_atom_id(), 'CA']),
  }))
}

function collectFrameworkCa(
  structure: object,
  excluded: Set<string>,
): Map<string, { x: number; y: number; z: number }> {
  const map = new Map<string, { x: number; y: number; z: number }>()
  const loci = StructureSelection.toLociWithCurrentUnits(caQuery()(new QueryContext(structure as never)))
  StructureElement.Loci.forEachLocation(loci, (loc) => {
    const chain =
      StructureProperties.chain.auth_asym_id(loc) ||
      StructureProperties.chain.label_asym_id(loc)
    const seq =
      StructureProperties.residue.auth_seq_id(loc) ??
      StructureProperties.residue.label_seq_id(loc)
    if (!chain || seq == null || Number.isNaN(Number(seq))) return
    const key = `${chain}:${Number(seq)}`
    if (excluded.has(key)) return
    const { conformation } = loc.unit
    map.set(key, {
      x: conformation.x(loc.element),
      y: conformation.y(loc.element),
      z: conformation.z(loc.element),
    })
  })
  return map
}

export async function superposeMolstarMobileOntoPivot(
  viewer: MolstarViewer,
  excludedResidueKeys: Iterable<string> = [],
): Promise<{ rmsd: number; n: number } | null> {
  const plugin = viewer.plugin
  const structures = plugin.managers.structure.hierarchy.current.structures
  if (structures.length < 2) return null
  const pivot = structures[0].cell.obj?.data
  const mobile = structures[1].cell.obj?.data
  if (!pivot || !mobile) return null
  const excluded = new Set(excludedResidueKeys)
  const pivotMap = collectFrameworkCa(pivot, excluded)
  const mobileMap = collectFrameworkCa(mobile, excluded)
  const keys = [...pivotMap.keys()].filter((key) => mobileMap.has(key))
  if (keys.length < 8) return null
  const positions = {
    a: MinimizeRmsd.Positions.empty(keys.length),
    b: MinimizeRmsd.Positions.empty(keys.length),
  }
  keys.forEach((key, i) => {
    const pa = pivotMap.get(key)!
    const pb = mobileMap.get(key)!
    positions.a.x[i] = pa.x
    positions.a.y[i] = pa.y
    positions.a.z[i] = pa.z
    positions.b.x[i] = pb.x
    positions.b.y[i] = pb.y
    positions.b.z[i] = pb.z
  })
  const fit = MinimizeRmsd.compute(positions)
  const b = plugin.state.data.build().to(structures[1].cell)
    .insert(StateTransforms.Model.TransformStructureConformation, {
      transform: { name: 'matrix', params: { data: fit.bTransform, transpose: false } },
    })
  await plugin.runTask(plugin.state.data.updateTree(b))
  plugin.canvas3d?.requestCameraReset()
  return { rmsd: fit.rmsd, n: keys.length }
}

