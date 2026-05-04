/* Qdrant 向量库状态卡片 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { registerCard } from '../CardRegistry'
import QdrantCardVue from '../QdrantCard/QdrantCard.vue'

export type QdrantBadge = 'loading' | 'ok' | 'err'

export interface QdrantCardData {
  ready: boolean
  host: string
  port: number
  disk_size?: number
}

export class QdrantCard {
  readonly badge = ref<QdrantBadge>('loading')
  readonly detail = ref('')

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 800)

  badgeClass(): string {
    if (this.badge.value === 'loading') return 'badge-loading'
    if (this.badge.value === 'ok') return 'badge-ok'
    return 'badge-err'
  }

  updateFromData(data: QdrantCardData): void {
    this.badge.value = data.ready ? 'ok' : 'err'
    if (data.ready) {
      const sizeGB = (data.disk_size / (1024**3)).toFixed(1)
      this.detail.value = `${data.host}:${data.port} · ${sizeGB}GB`
    } else {
      this.detail.value = ''
    }
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/qdrant')
      this.updateFromData(st)
    } catch {
      this.badge.value = 'err'
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

// 主动注册
const _card = new QdrantCard()
registerCard({
  name: 'qdrant',
  component: QdrantCardVue,
  cardClass: _card,
})
