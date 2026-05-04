/* 设备信息卡片 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { registerCard } from '../CardRegistry'
import DeviceCardVue from '../DeviceCard/DeviceCard.vue'

export interface SystemInfo {
  cpu_percent?: number
  memory_percent?: number
  gpu_name?: string
  gpu_memory_used?: number
  gpu_memory_total?: number
  disk_used?: number
  disk_total?: number
  uptime?: number
}

export class DeviceCard {
  readonly info = ref<SystemInfo | null>(null)

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 1000, 500)

  updateFromData(data: SystemInfo): void {
    this.info.value = { ...this.info.value, ...data }
  }

  async poll(): Promise<void> {
    try {
      const info = await this._api.fetchJson<SystemInfo>('/overview/system-info')
      this.updateFromData(info)
    } catch {
      // ignore
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

// 主动注册
const _card = new DeviceCard()
registerCard({
  name: 'device',
  component: DeviceCardVue,
  cardClass: _card,
})
