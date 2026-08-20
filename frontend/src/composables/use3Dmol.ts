import type {
  InterfaceChainMeta,
  Mol3DViewer,
  ViewerColorMode,
} from '@/types/structure'

export type { Mol3DViewer, ViewerColorMode } from '@/types/structure'

let mol3dLoadPromise: Promise<void> | null = null

/** Prefer local vendor copy; fall back to CDN if missing. */
const MOL3D_SOURCES = [
  '/vendor/3Dmol-min.js',
  'https://3Dmol.org/build/3Dmol-min.js',
]

/**
 * PyMOL-like cartoon: cylindrical helices + directional sheet arrows.
 * 3Dmol assigns secondary structure from backbone geometry when CIF lacks SS records.
 */
export const PYMOL_CARTOON = {
  style: 'rectangle',
  arrows: true,
  tubes: true,
  thickness: 0.55,
  width: 1.4,
} as const

export function cartoonStyle(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return { ...PYMOL_CARTOON, ...extra }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error(`无法加载 ${src}`))
    document.head.appendChild(script)
  })
}

/** Dynamically load 3Dmol.js. */
export function load3DmolLib(): Promise<void> {
  if (window.$3Dmol) return Promise.resolve()
  if (!mol3dLoadPromise) {
    mol3dLoadPromise = (async () => {
      let lastError: unknown
      for (const src of MOL3D_SOURCES) {
        try {
          await loadScript(src)
          if (window.$3Dmol) return
        } catch (err) {
          lastError = err
        }
      }
      mol3dLoadPromise = null
      throw lastError instanceof Error ? lastError : new Error('3D 库加载失败')
    })()
  }
  return mol3dLoadPromise
}

export function createViewer(
  container: HTMLElement,
  backgroundColor = '0xf1f5f9',
): Mol3DViewer {
  if (!window.$3Dmol) {
    throw new Error('3Dmol 尚未加载')
  }
  container.innerHTML = ''
  const viewer = window.$3Dmol.createViewer(container, {
    backgroundColor,
    cartoonQuality: 22,
    antialias: true,
  })
  // Soft edge outline improves helix/sheet silhouette (closer to PyMOL depth cues).
  if (typeof viewer.setViewStyle === 'function') {
    viewer.setViewStyle({ style: 'outline', color: '0x334155', width: 0.05 })
  }
  if (typeof viewer.setDefaultCartoonQuality === 'function') {
    viewer.setDefaultCartoonQuality(22)
  }
  return viewer
}

export function destroyViewer(viewer: Mol3DViewer | null, container?: HTMLElement | null): void {
  if (container) container.innerHTML = ''
  if (viewer?.clear) viewer.clear()
}

/** Force WebGL canvas to match container size after it becomes visible. */
export function resizeViewer(viewer: Mol3DViewer | null): void {
  if (!viewer) return
  if (typeof viewer.resize === 'function') viewer.resize()
  viewer.render()
}

/** AlphaFold/Boltz-style pLDDT color (B-factor in mmCIF, 0–100). */
export function plddtToColor(b: number | null | undefined): number {
  if (b == null || Number.isNaN(b)) return 0x8b949e
  let v = b
  if (v <= 1.0) v *= 100
  if (v > 90) return 0x0053d6
  if (v > 70) return 0x00c1f2
  if (v > 50) return 0xfffd00
  return 0xff7d00
}

export function hexColorToInt(hex: string | undefined | null): number {
  if (!hex) return 0x8b949e
  const s = hex.replace('#', '')
  return parseInt(s, 16)
}

export function applyPlddtStyle(v: Mol3DViewer): void {
  v.setStyle({}, {
    cartoon: cartoonStyle({
      colorfunc: (atom: { b?: number }) => plddtToColor(atom.b),
    }),
  })
}

export function applyChainStyle(v: Mol3DViewer, chains: InterfaceChainMeta[]): void {
  v.setStyle({}, {})
  for (const ch of chains) {
    v.setStyle({ chain: ch.chain_id }, {
      cartoon: cartoonStyle({
        color: hexColorToInt(ch.color),
        opacity: 1,
      }),
    })
  }
}

export function applyViewerStyles(
  v: Mol3DViewer,
  mode: ViewerColorMode,
  chains?: InterfaceChainMeta[] | null,
): void {
  if (!v) return
  if (mode === 'plddt') {
    applyPlddtStyle(v)
  } else if (chains?.length) {
    applyChainStyle(v, chains)
  } else {
    applyPlddtStyle(v)
  }
}
