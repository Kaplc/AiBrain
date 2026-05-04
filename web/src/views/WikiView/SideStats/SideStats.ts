import { wikiViewModel } from '../WikiViewModel'

export function useSideStats() {
  return {
    fileCount: () => wikiViewModel.rawFiles.value.length || '-',
    totalSize: () => wikiViewModel.rawFiles.value.length
      ? wikiViewModel.formatSize(wikiViewModel.totalSize)
      : '-',
    indexStatus: wikiViewModel.indexStatusText,
  }
}
