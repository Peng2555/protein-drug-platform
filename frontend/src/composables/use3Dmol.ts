import type {
  InterfaceChainMeta,
  Mol3DViewer,
  ViewerColorMode,
} from '@/types/structure'

export type { Mol3DViewer, ViewerColorMode } from '@/types/structure'

let mol3dLoadPromise: Promise<void> | null = null

/** Dynamically load 3Dmol.js (same CDN as legacy app.js). */
export function load3DmolLib(): Promise<void> {
  if (window.$3Dmol) return Promise.resolve()
  if (!mol3dLoadPromise) {
    mol3dLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://3Dmol.org/build/3Dmol-min.js'
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('3D 库加载失败'))
      document.head.appendChild(script)
    })
  }
  return mol3dLoadPromise
}

export function createViewer(
  container: HTMLElement,
  backgroundColor = '0xeef2f7',
): Mol3DViewer {
  if (!window.$3Dmol) {
    throw new Error('3Dmol 尚未加载')
  }
  container.innerHTML = ''
  return window.$3Dmol.createViewer(container, { backgroundColor })
}

export function destroyViewer(viewer: Mol3DViewer | null, container?: HTMLElement | null): void {
  if (container) container.innerHTML = ''
  if (viewer?.clear) viewer.clear()
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
    cartoon: {
      colorfunc: (atom: { b?: number }) => plddtToColor(atom.b),
    },
  })
}

export function applyChainStyle(v: Mol3DViewer, chains: InterfaceChainMeta[]): void {
  v.setStyle({}, {})
  for (const ch of chains) {
    v.setStyle({ chain: ch.chain_id }, {
      cartoon: { color: hexColorToInt(ch.color), opacity: 0.92 },
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
