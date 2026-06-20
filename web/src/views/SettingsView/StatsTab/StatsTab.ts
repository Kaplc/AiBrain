/* StatsTab — Token 用量 + 余额
 *
 * 作用：以独立 Tab 展示 LLM Token 消耗统计和 DeepSeek 账户余额。
 * 复用 OverviewView 已有 card singleton（balanceCard / tokenCard）的数据与轮询逻辑，
 * 生命周期由本 Tab 的 onMounted/onUnmounted 接管。
 */
import { registerTab } from '../TabRegistry'
import StatsTabVue from './StatsTab.vue'

// 直接从 OverviewView 取 card singleton（已全局注册，含轮询/数据逻辑）
import { balanceCard } from '../../OverviewView/BalanceCard/BalanceCard'
import { tokenCard } from '../../OverviewView/TokenCard/TokenCard'

export class StatsTab {
  readonly balance = balanceCard
  readonly token = tokenCard

  /** 立即启动轮询（模块加载即开始，不依赖 SettingsView 生命周期） */
  constructor() {
    this.balance.start()
    this.token.start()
  }
}

export const statsTab = new StatsTab()
registerTab({
  name: 'stats',
  title: '用量',
  component: StatsTabVue,
  tabClass: statsTab,
})
