/* Wiki tab - Wiki 配置 */
import { reactive } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { ConfigField } from '@/stores/config'
import { registerTab } from '../TabRegistry'
import WikiTabVue from '../WikiTab/WikiTab.vue'
import { Mem0Tab } from '../Mem0Tab/Mem0Tab'
export type { SectionFormState } from '../Mem0Tab/Mem0Tab'

export class WikiTab {
  readonly form = reactive<SectionFormState>({ fields: [], values: {}, defaults: {} })
  readonly dirChecks = reactive<Record<string, 'ok' | 'err' | ''>>({})

  private _api = useApi()
  private _toast = useToast()

  buildForm(fields?: ConfigField[]): void {
    this.form.fields = fields ?? []
    this.form.values = {}
    this.form.defaults = {}
    for (const f of this.form.fields) {
      this.form.values[f.key] = String(f.value ?? '')
      this.form.defaults[f.key] = String(f.default ?? '')
    }
  }

  collectData(): Record<string, any> {
    const data: Record<string, any> = {}
    for (const f of this.form.fields) {
      const raw = this.form.values[f.key] ?? ''
      const val = f.type === 'number' ? (parseInt(raw) || 0) : raw
      data[f.key] = val
    }
    return data
  }

  async save(): Promise<void> {
    if (!this.form.fields.length) return
    try {
      const r = await this._api.postJson<any>('/settings/save-aibrain-config', { wiki: this.collectData() })
      if (r.error) {
        this._toast.show('保存失败: ' + r.error, 'error')
      } else {
        this._toast.show('✅ wiki.json 已保存', 'success')
      }
    } catch (e: any) {
      this._toast.show('保存失败: ' + e, 'error')
    }
  }

  reset(): void {
    for (const f of this.form.fields) {
      this.form.values[f.key] = String(f.default ?? '')
    }
    this._toast.show('已恢复默认', 'info')
  }

  async browseDir(key: string): Promise<void> {
    try {
      const data = await this._api.postJson<{ path?: string }>('/settings/select-directory', {})
      if (data.path) {
        this.form.values[key] = data.path
        this.checkDir(`wiki_${key}`, data.path)
      }
    } catch {
      const native = document.createElement('input')
      native.type = 'file'
      native.webkitdirectory = true
      native.onchange = () => {
        if (native.files && native.files[0]) {
          this.form.values[key] = native.files[0].webkitRelativePath.split('/')[0]
          this.checkDir(`wiki_${key}`, this.form.values[key])
        }
      }
      native.click()
    }
  }

  async checkDir(inputId: string, path?: string): Promise<void> {
    if (!path) {
      path = (this.form.values[inputId.replace('wiki_', '')] ?? '').trim()
    }
    if (!path) {
      this.dirChecks[inputId] = ''
      return
    }
    try {
      const data = await this._api.postJson<{ exists: boolean }>('/settings/check-path', { path })
      this.dirChecks[inputId] = data.exists ? 'ok' : 'err'
    } catch {
      this.dirChecks[inputId] = ''
    }
  }

  async loadFromConfig(cfg: any, st: any, aibrain: any): Promise<void> {
    const section = aibrain?.wiki
    if (section?.fields) {
      this.buildForm(section.fields)
    }
  }

  initDirChecks(): void {
    for (const f of this.form.fields) {
      if (f.type !== 'dir') continue
      const inputId = `wiki_${f.key}`
      const val = this.form.values[f.key] ?? ''
      if (val.trim()) this.checkDir(inputId, val)
    }
  }

  onInput(key: string): void {
    this.checkDir(`wiki_${key}`, this.form.values[key])
  }
}

// 主动注册
const _wikiTab = new WikiTab()
registerTab({
  name: 'wiki',
  title: 'wiki.json',
  component: WikiTabVue,
  tabClass: _wikiTab,
})
