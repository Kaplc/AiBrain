/* LLM tab - 通用 LLM 配置
 *
 * 作用：管理 ~/.aibrain/config/llm.json（provider/model/api_key/base_url/...）
 * 实现：固定字段表单（不用动态 build_fields），Test Connection 按钮真发一次请求验证连通性
 *
 * 接口协议分组（后端 settings_mod.LLM_PROVIDER_GROUPS 决定）：
 *   - OpenAI 兼容 (openai SDK)     →  POST {base_url}/chat/completions
 *   - Anthropic 兼容 (anthropic SDK) →  POST {base_url}/messages
 */

import { reactive, ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { ConfigField } from '@/stores/config'
import { registerTab } from '../TabRegistry'
import LLMTabVue from '../LLMTab/LLMTab.vue'

// 接口协议 → API 路径提示
const API_PATH_HINTS: Record<string, string> = {
  openai: '/v1/chat/completions',
  anthropic: '/v1/messages',
}

export interface LLMFormState {
  fields: ConfigField[]
  values: Record<string, any>
  defaults: Record<string, any>
  optionGroups?: { label: string; protocol: string; providers: string[] }[]
}

export class LLMTab {
  readonly form = reactive<LLMFormState>({
    fields: [], values: {}, defaults: {}, optionGroups: [],
  })
  readonly testStatus = ref<'' | 'testing' | 'ok' | 'err'>('')
  readonly testMessage = ref('')
  readonly testLatency = ref(0)

  private _api = useApi()
  private _toast = useToast()

  /* currentProtocol：当前选中 provider 对应的协议 */
  get currentProtocol(): 'openai' | 'anthropic' | '' {
    const provider = String(this.form.values['provider'] ?? '')
    const groups = this.form.optionGroups ?? []
    for (const g of groups) {
      if (g.providers.includes(provider)) return g.protocol as any
    }
    return ''
  }

  /* currentApiPath：根据协议返回 API 路径提示 */
  get currentApiPath(): string {
    return API_PATH_HINTS[this.currentProtocol] ?? '/v1/...'
  }

  /* currentProtocolLabel：协议的中文标签（用于徽章） */
  get currentProtocolLabel(): string {
    const groups = this.form.optionGroups ?? []
    for (const g of groups) {
      if (g.protocol === this.currentProtocol) return g.label
    }
    return ''
  }

  /* buildForm：根据字段定义构建表单 */
  buildForm(fields?: ConfigField[]): void {
    this.form.fields = fields ?? []
    this.form.values = {}
    this.form.defaults = {}
    this.form.optionGroups = []
    for (const f of this.form.fields) {
      this.form.values[f.key] = f.value ?? ''
      this.form.defaults[f.key] = f.default ?? ''
      if (f.key === 'provider') {
        this.form.optionGroups = (f as any).optionGroups ?? []
      }
    }
  }

  /* collectData：收集表单数据，处理 number 类型 */
  collectData(): Record<string, any> {
    const data: Record<string, any> = {}
    for (const f of this.form.fields) {
      const raw = this.form.values[f.key] ?? ''
      const val = f.type === 'number' ? (parseFloat(raw) || 0) : raw
      data[f.key] = val
    }
    return data
  }

  /* save：保存 LLM 配置 */
  async save(): Promise<void> {
    if (!this.form.fields.length) return
    try {
      const r = await this._api.postJson<any>('/settings/save-aibrain-config', { llm: this.collectData() })
      if (r?.error) {
        this._toast.show('保存失败: ' + r.error, 'error')
      } else {
        this._toast.show('✅ llm.json 已保存', 'success')
      }
    } catch (e: any) {
      this._toast.show('保存失败: ' + e, 'error')
    }
  }

  /* testConnection：用当前表单值真发一次请求验证连通性 */
  async testConnection(): Promise<void> {
    this.testStatus.value = 'testing'
    this.testMessage.value = '正在测试...'
    this.testLatency.value = 0
    try {
      const r = await this._api.postJson<{
        ok: boolean; message: string; response?: string; latency_ms?: number
      }>('/settings/llm/test', this.collectData())
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
    for (const f of this.form.fields) {
      this.form.values[f.key] = f.default ?? ''
    }
    this.testStatus.value = ''
    this.testMessage.value = ''
    this._toast.show('已恢复默认', 'info')
  }

  /* onProviderChange：切换接口类型时自动填默认 model/base_url
   * UI 上只有 openai / anthropic 两个选项
   */
  onProviderChange(provider: string): void {
    const knownDefaults: Record<string, { model: string; base_url: string }> = {
      openai:    { model: 'gpt-4o-mini',              base_url: '' },
      anthropic: { model: 'claude-sonnet-4-20250514', base_url: '' },
    }
    const def = knownDefaults[provider]
    if (!def) return
    const currentModel = String(this.form.values['model'] ?? '')
    const currentUrl = String(this.form.values['base_url'] ?? '')
    if (!currentModel || Object.values(knownDefaults).some(d => d.model === currentModel)) {
      this.form.values['model'] = def.model
    }
    if (!currentUrl || Object.values(knownDefaults).some(d => d.base_url === currentUrl)) {
      this.form.values['base_url'] = def.base_url
    }
  }

  /* loadFromConfig：从 aibrain.llm 加载字段 */
  async loadFromConfig(cfg: any, st: any, aibrain: any): Promise<void> {
    const section = aibrain?.llm
    if (section?.fields) {
      this.buildForm(section.fields)
    }
  }
}

// 主动注册
const _llmTab = new LLMTab()
registerTab({
  name: 'llm',
  title: 'LLM',
  component: LLMTabVue,
  tabClass: _llmTab,
})
