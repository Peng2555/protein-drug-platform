import { QualityAssessmentProvider } from 'molstar/lib/extensions/model-archive/quality-assessment/prop'
import { Viewer } from 'molstar/lib/apps/viewer/app'
import { Bond, StructureElement, StructureProperties, Unit } from 'molstar/lib/mol-model/structure'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
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
  illumination: true,
} as const

export async function createMolstarViewer(
  container: HTMLElement,
  options: Record<string, unknown> = {},
): Promise<MolstarViewer> {
  container.innerHTML = ''
  container.style.position = 'relative'
  container.style.width = '100%'
  container.style.height = '100%'
  return Viewer.create(container, { ...VIEWER_OPTIONS, ...options }).then((viewer) => {
    registerBoltzPlddtTheme(viewer.plugin)
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
): Promise<void> {
  const fmt = format ?? detectStructureFormat(text)
  await viewer.loadStructureFromData(text, fmt, { dataLabel: 'structure' })
  viewer.plugin.canvas3d?.requestCameraReset()
}

export type MolstarReprKind = 'molecular-surface' | 'polymer-cartoon'

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
    description: 'Hydrophobic surface patches (FILMWVY, RSA≥0.25).',
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
  if (!residues.length) {
    viewer.plugin.canvas3d?.requestCameraReset()
    return
  }
  viewer.structureInteractivity({
    action: 'focus',
    elements: {
      items: residues.map((r) => ({
        auth_asym_id: r.chain_id,
        auth_seq_id: r.seq_num,
      })),
    },
  })
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
