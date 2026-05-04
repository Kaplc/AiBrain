/* Flask 服务状态卡片 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { registerCard } from '../CardRegistry'
import FlaskCardVue from '../FlaskCard/FlaskCard.vue'

export type FlaskBadge = 'ok' | 'err' | 'restarting' | 'yellow'

export interface FlaskCardData {
  pid: number
  port: number
  uptime?: number
}

export class FlaskCard {
  readonly badge = ref<FlaskBadge>('ok')
  readonly restarting = ref(false)
  readonly restartSeconds = ref(0)
  readonly detail = ref('')
  readonly uptime = ref(0)

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 2000, 1600)
  private _restartTimer: number | null = null

  badgeClass(): string {
    if (this.badge.value === 'ok') return 'badge-ok'
    if (this.badge.value === 'restarting') return 'badge-loading'
    return 'badge-err'
  }

  updateFromData(data: FlaskCardData): void {
    this.badge.value = 'ok'
    this.detail.value = `PID: ${data.pid} · 端口: ${data.port}`
    this.uptime.value = data.uptime || 0
  }

  async poll(): Promise<void> {
    try {
      const st = await this._api.fetchJson<any>('/overview/flask')
      this.updateFromData(st)
    } catch {
      // ignore
    }
  }

  async restart(): Promise<void> {
    if (this.restarting.value) return
    this.restarting.value = true
    this.restartSeconds.value = 0
    try {
      await this._api.postJson('/overview/flask/restart', {})
      const countdown = setInterval(() => {
        this.restartSeconds.value++
        if (this.restartSeconds.value >= 15) {
          clearInterval(countdown)
          this.restarting.value = false
        }
      }, 1000)
      this._restartTimer = countdown
    } catch {
      this.restarting.value = false
    }
  }

  cleanup(): void {
    if (this._restartTimer !== null) {
      clearInterval(this._restartTimer)
      this._restartTimer = null
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }
}

// 主动注册
const _card = new FlaskCard()
registerCard({
  name: 'flask',
  component: FlaskCardVue,
  cardClass: _card,
})
