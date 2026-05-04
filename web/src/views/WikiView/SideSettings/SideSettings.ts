import { wikiViewModel } from '../WikiViewModel'

export function useSideSettings() {
  return {
    formWikiDir: wikiViewModel.formWikiDir,
    formLightragDir: wikiViewModel.formLightragDir,
    formLanguage: wikiViewModel.formLanguage,
    formChunkSize: wikiViewModel.formChunkSize,
    formTimeout: wikiViewModel.formTimeout,
    saving: wikiViewModel.saving,
    saveSettings: () => wikiViewModel.saveSettings(),
  }
}
