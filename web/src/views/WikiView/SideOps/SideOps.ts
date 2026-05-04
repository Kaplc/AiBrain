import { wikiViewModel } from '../WikiViewModel'

export function useSideOps() {
  return {
    showProgress: wikiViewModel.showProgress,
    rebuildIndex: () => wikiViewModel.rebuildIndex(),
    progressLabel: wikiViewModel.progressLabel,
    progressPct: wikiViewModel.progressPct,
    logLines: wikiViewModel.logLines,
    logWrapEl: wikiViewModel.logWrapEl,
    indexResultMsg: wikiViewModel.indexResultMsg,
  }
}
