/* DeepSeek 余额卡片
 *
 * 作用：显示 DeepSeek 账户余额、可用状态和进度条
 * 实现：每 30 秒轮询 /overview/balance
 */

import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { registerCard } from '../CardRegistry'
import BalanceCardVue from './BalanceCard.vue'

export interface BalanceInfo {
  currency: string
  total_balance: string
  granted_balance: string
  topped_up_balance: string
}

export interface BalanceData {
  is_available: boolean
  balance_infos?: BalanceInfo[]
  error?: string
}

export class BalanceCard {
  readonly loading = ref(true)
  readonly error = ref('')
  readonly available = ref(false)
  readonly balanceList = ref<BalanceInfo[]>([])

  private _api = useApi()
  private _polling = usePolling(() => this.poll(), 30000, 0)

  async poll(): Promise<void> {
    try {
      const data = await this._api.fetchJson<BalanceData>('/overview/balance', 3)
      if (data.error) {
        this.error.value = data.error
        this.loading.value = false
        return
      }
      this.available.value = data.is_available
      this.balanceList.value = data.balance_infos || []
      this.loading.value = false
      this.error.value = ''
    } catch (e: any) {
      this.error.value = e.message || '请求失败'
      this.loading.value = false
    }
  }

  start(): void { this._polling.start() }
  stop(): void { this._polling.stop() }

  /** 格式化余额显示（保留两位小数） */
  formatBalance(val: string): string {
    const n = parseFloat(val)
    return isNaN(n) ? val : n.toFixed(2)
  }
}

export const balanceCard = new BalanceCard()
registerCard({
  name: 'balance',
  component: BalanceCardVue,
  cardClass: balanceCard,
})
