import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { InterfaceChainMeta, Mol3DViewer, SelectedResidue, ViewerColorMode } from '@/types/structure'
import { cartoonStyle, hexColorToInt, plddtToColor } from '@/composables/use3Dmol'

export type { SelectedResidue } from '@/types/structure'

/** PyMOL default selection color & dimming factors (legacy app.js). */
export const PYMOL_SEL_COLOR = 0xff00ff
export const PYMOL_SEL_DIM = 0.22
export const PYMOL_CHAIN_DIM = 0.38

export function residueSelectionKey(chainId: string, resi: number): string {
  return `${chainId}:${parseInt(String(resi), 10)}`
}

export function applyPyMOLSelectionView(
  v: Mol3DViewer,
  mode: ViewerColorMode,
  chains?: InterfaceChainMeta[] | null,
  selected: SelectedResidue[] = [],
): void {
  if (!selected.length) return

  const chainsWithSel = new Set(selected.map((r) => r.chainId))
  const orSel = selected.map((r) => ({ chain: r.chainId, resi: r.resi }))

  if (mode === 'plddt') {
    v.setStyle({}, {
      cartoon: cartoonStyle({
        colorfunc: (atom: { b?: number }) => plddtToColor(atom.b),
        opacity: PYMOL_SEL_DIM,
      }),
    })
  } else if (chains?.length) {
    for (const ch of chains) {
      v.setStyle({ chain: ch.chain_id }, {
        cartoon: cartoonStyle({
          color: hexColorToInt(ch.color),
          opacity: chainsWithSel.has(ch.chain_id) ? PYMOL_CHAIN_DIM : PYMOL_SEL_DIM,
        }),
      })
    }
  } else {
    v.setStyle({}, { cartoon: cartoonStyle({ opacity: PYMOL_SEL_DIM }) })
  }

  for (const cid of chainsWithSel) {
    v.addStyle({ chain: cid }, { cartoon: cartoonStyle({ opacity: 0.5 }) })
  }

  v.addStyle({ or: orSel }, {
    cartoon: cartoonStyle({ color: PYMOL_SEL_COLOR, opacity: 1, thickness: 0.62, width: 1.55 }),
  })
}

export const useSelectionStore = defineStore('structureSelection', () => {
  const selectedSeqResidues = ref(new Map<string, SelectedResidue>())
  const lastSeqPickAnchor = ref<SelectedResidue | null>(null)

  function getSelectedResiduesList(): SelectedResidue[] {
    return [...selectedSeqResidues.value.values()]
  }

  function isResidueSelected(chainId: string, resi: number): boolean {
    return selectedSeqResidues.value.has(residueSelectionKey(chainId, resi))
  }

  function commitSelection(next: Map<string, SelectedResidue>): void {
    selectedSeqResidues.value = next
  }

  function selectSequenceResidue(
    chainId: string,
    resi: number,
    event?: Pick<MouseEvent, 'shiftKey' | 'ctrlKey' | 'metaKey'>,
  ): void {
    const resiNum = parseInt(String(resi), 10)
    const key = residueSelectionKey(chainId, resiNum)
    const shift = event?.shiftKey
    const ctrl = event?.ctrlKey || event?.metaKey
    const next = new Map(selectedSeqResidues.value)

    if (shift && lastSeqPickAnchor.value?.chainId === chainId) {
      const a = Math.min(lastSeqPickAnchor.value.resi, resiNum)
      const b = Math.max(lastSeqPickAnchor.value.resi, resiNum)
      for (let i = a; i <= b; i += 1) {
        next.set(residueSelectionKey(chainId, i), { chainId, resi: i })
      }
      lastSeqPickAnchor.value = { chainId, resi: resiNum }
    } else if (ctrl) {
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.set(key, { chainId, resi: resiNum })
        lastSeqPickAnchor.value = { chainId, resi: resiNum }
      }
    } else if (next.has(key)) {
      next.delete(key)
    } else {
      next.set(key, { chainId, resi: resiNum })
      lastSeqPickAnchor.value = { chainId, resi: resiNum }
    }

    commitSelection(next)
  }

  function clearSequenceResidueSelection(): void {
    commitSelection(new Map())
    lastSeqPickAnchor.value = null
  }

  function bindViewerResiduePick(
    v: Mol3DViewer,
    onPick?: (chainId: string, resi: number, event: MouseEvent) => void,
  ): void {
    v.setClickable({}, true, (atom, _viewer, event) => {
      if (!atom || atom.resi == null || !atom.chain) return
      selectSequenceResidue(atom.chain, atom.resi, event)
      onPick?.(atom.chain, atom.resi, event)
    })
  }

  return {
    selectedSeqResidues,
    lastSeqPickAnchor,
    getSelectedResiduesList,
    isResidueSelected,
    selectSequenceResidue,
    clearSequenceResidueSelection,
    bindViewerResiduePick,
  }
})
