/* ChatTab - 意识流 Chat 配置
 *
 * 作用：管理 ~/.aibrain/config/chat.json
 * 字段：chat_provider, chat_model, chat_api_key, chat_base_url,
 *       idle_enabled, idle_interval_seconds, system_persona, ...
 */

import { reactive, ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { registerTab } from '../TabRegistry'
import ChatTabVue from './ChatTab.vue'

// provider → 默认值映射
const PROVIDER_DEFAULTS: Record<string, { model: string; base_url: string }> = {
  openai:    { model: 'gpt-4o-mini',              base_url: '' },
  anthropic: { model: 'claude-sonnet-4-20250514', base_url: '' },
  deepseek:  { model: 'deepseek-chat',            base_url: 'https://api.deepseek.com/v1' },
  ollama:    { model: 'qwen2.5:7b',               base_url: 'http://localhost:11434/v1' },
  lmstudio:  { model: 'local-model',              base_url: 'http://localhost:1234/v1' },
  minimax:   { model: 'MiniMax-M2.7',             base_url: 'https://api.minimaxi.com/v1' },
}
const PROVIDER_OPTIONS = Object.keys(PROVIDER_DEFAULTS)

export class ChatTab {
  readonly form = reactive<Record<string, any>>({})
  readonly defaults = reactive<Record<string, any>>({})
  readonly testStatus = ref<'' | 'testing' | 'ok' | 'err'>('')
  readonly testMessage = ref('')
  readonly testLatency = ref(0)

  private _api = useApi()
  private _toast = useToast()

  get providerOptions() { return PROVIDER_OPTIONS }

  /* buildForm：从后端 data/defaults 构建表单 */
  buildForm(data: Record<string, any>, defs: Record<string, any>): void {
    Object.keys(defs).forEach(k => {
      this.form[k] = data[k] ?? defs[k]
      this.defaults[k] = defs[k]
    })
  }

  /* onProviderChange：切换 provider 自动填默认 model/base_url */
  onProviderChange(provider: string): void {
    const def = PROVIDER_DEFAULTS[provider]
    if (!def) return
    const curModel = String(this.form['chat_model'] ?? '')
    const curUrl = String(this.form['chat_base_url'] ?? '')
    // 如果当前值是某个 provider 的默认值 → 替换
    const allModels = Object.values(PROVIDER_DEFAULTS).map(d => d.model)
    const allUrls = Object.values(PROVIDER_DEFAULTS).map(d => d.base_url).filter(Boolean)
    if (!curModel || allModels.includes(curModel)) {
      this.form['chat_model'] = def.model
    }
    if (!curUrl || allUrls.includes(curUrl)) {
      this.form['chat_base_url'] = def.base_url
    }
  }

  /* save：保存配置 */
  async save(): Promise<void> {
    try {
      const r = await this._api.postJson<any>('/settings/chat', { ...this.form })
      if (r?.error) {
        this._toast.show('保存失败: ' + r.error, 'error')
      } else {
        this._toast.show('✅ Chat 配置已保存，下次 tick 生效', 'success')
      }
    } catch (e: any) {
      this._toast.show('保存失败: ' + e, 'error')
    }
  }

  /* testConnection：测试连通性 */
  async testConnection(): Promise<void> {
    this.testStatus.value = 'testing'
    this.testMessage.value = '正在测试...'
    this.testLatency.value = 0
    try {
      const r = await this._api.postJson<{
        ok: boolean; message: string; response?: string; latency_ms?: number
      }>('/settings/chat/test', { ...this.form })
      if (r.ok) {
        this.testStatus.value = 'ok'
        this.testMessage.value = r.message
        this.testLatency.value = r.latency_ms ?? 0
        this._toast.show(`✅ ${r.message} (${r.latency_ms}ms)`, 'success')
      } else {
        this.testStatus.value = 'err'
        this.testMessage.value = r.message
        this._toast.show('❌ ' + r.message, 'error')
      }
    } catch (e: any) {
      this.testStatus.value = 'err'
      this.testMessage.value = String(e)
      this._toast.show('❌ ' + e, 'error')
    }
  }

  /* reset：恢复默认值 */
  reset(): void {
    Object.keys(this.defaults).forEach(k => {
      this.form[k] = this.defaults[k]
    })
    this.testStatus.value = ''
    this.testMessage.value = ''
    this._toast.show('已恢复默认', 'info')
  }

  /* loadFromConfig：由 SettingsViewModel 调用 */
  async loadFromConfig(cfg: any, st: any, aibrain: any): Promise<void> {
    try {
      const r = await this._api.fetchJson<{ data: any; defaults: any }>('/settings/chat')
      if (r?.data) {
        this.buildForm(r.data, r.defaults || {})
      }
    } catch (e) {
      console.error('[ChatTab] load failed:', e)
    }
  }
}

// 注册 Tab
const _chatTab = new ChatTab()
registerTab({
  name: 'chat',
  title: 'Chat',
  component: ChatTabVue,
  tabClass: _chatTab,
})
