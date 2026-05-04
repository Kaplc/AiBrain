/* 模型状态卡片 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { registerCard } from '../CardRegistry'
import ModelCardVue from '../ModelCard/ModelCard.vue'

export type ModelBadge = 'loading' | 'ok' | 'err'

export interface ModelCardData {
  loaded: boolean
  embedding_model?: string
  embedding_dim?: number
}

export class ModelCard {
  readonly badge = ref<ModelBadge>('loading')
  readonly subText = ref('加载中...')
  readonly detail = ref('')

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 0)

  badgeClass(): string {
    if (this.badge.value === 'loading') return 'badge-loading'
    if (this.badge.value === 'ok') return 'badge-ok'
    return 'badge-err'
  }

  updateFromData(data: ModelCardData): void {
    if (data.loaded) {
      this.badge.value = 'ok'
      this.subText.value = '模型就绪'
      this.detail.value = data.embedding_model ? `${data.embedding_model} · ${data.embedding_dim}d` : ''
    } else {
      this.badge.value = 'loading'
      this.subText.value = '加载中...'
      this.detail.value = ''
    }
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/model')
      this.updateFromData(st)
    } catch {
      this.badge.value = 'err'
      this.subText.value = '模型加载失败'
      this.detail.value = ''
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

// 主动注册
const _card = new ModelCard()
registerCard({
  name: 'model',
  component: ModelCardVue,
  cardClass: _card,
})
