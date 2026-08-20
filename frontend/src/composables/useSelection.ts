import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { MolstarViewer } from '@/composables/useMolstar'
import { bindMolstarResiduePick, syncMolstarSelection } from '@/composables/useMolstar'
import type { SelectedResidue } from '@/types/structure'

export type { SelectedResidue } from '@/types/structure'

export function residueSelectionKey(chainId: string, resi: number): string {
  return `${chainId}:${parseInt(String(resi), 10)}`
}

export const useSelectionStore = defineStore('structureSelection', () => {
  const selectedSeqResidues = ref(new Map<string, SelectedResidue>())
  const lastSeqPickAnchor = ref<SelectedResidue | null>(null)
  let activeViewer: MolstarViewer | null = null

  function getSelectedResiduesList(): SelectedResidue[] {
    return [...selectedSeqResidues.value.values()]
  }

  function isResidueSelected(chainId: string, resi: number): boolean {
    return selectedSeqResidues.value.has(residueSelectionKey(chainId, resi))
  }

  function commitSelection(next: Map<string, SelectedResidue>): void {
    selectedSeqResidues.value = next
    if (activeViewer) syncMolstarSelection(activeViewer, getSelectedResiduesList())
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
    viewer: MolstarViewer,
    onPick?: (chainId: string, resi: number, event: Pick<MouseEvent, 'shiftKey' | 'ctrlKey' | 'metaKey'>) => void,
  ): void {
    activeViewer = viewer
    bindMolstarResiduePick(viewer, (chainId, resi, event) => {
      selectSequenceResidue(chainId, resi, event)
      onPick?.(chainId, resi, event)
    })
    syncMolstarSelection(viewer, getSelectedResiduesList())
  }

  function detachViewer(): void {
    activeViewer = null
  }

  return {
    selectedSeqResidues,
    lastSeqPickAnchor,
    getSelectedResiduesList,
    isResidueSelected,
    selectSequenceResidue,
    clearSequenceResidueSelection,
    bindViewerResiduePick,
    detachViewer,
  }
})
