/* StatsView — Token 用量 + 余额（独立页面）
 *
 * 复用 OverviewView 已有 card singleton 的数据与轮询逻辑，
 * 页面级生命周期由 vue-router 管理。
 */
import { balanceCard } from '../OverviewView/BalanceCard/BalanceCard'
import { tokenCard } from '../OverviewView/TokenCard/TokenCard'

export class StatsViewModel {
  readonly balance = balanceCard
  readonly token = tokenCard
}

export const statsViewModel = new StatsViewModel()
