import { wikiViewModel } from '../WikiViewModel'

export function useFileList() {
  return {
    loading: wikiViewModel.loading,
    loadError: wikiViewModel.loadError,
    sortedFiles: () => wikiViewModel.sortedFiles,
    doSort: (key: 'filename' | 'sizeBytes' | 'modified') => wikiViewModel.doSort(key),
    sortArrow: (key: 'filename' | 'sizeBytes' | 'modified') => wikiViewModel.sortArrow(key),
    copyPath: (path: string) => wikiViewModel.copyPath(path),
    formatSize: (bytes: number) => wikiViewModel.formatSize(bytes),
    formatDate: (ts: number) => wikiViewModel.formatDate(ts),
  }
}
