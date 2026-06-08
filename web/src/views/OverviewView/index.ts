/* 总览视图模型
 *
 * 作用：作为 OverviewView 的顶层 ViewModel，管理所有卡片实例的生命周期
 * 图表/统计逻辑 → MemoryCard/MemoryCard.ts
 * 各卡片逻辑   → ModelCard/ModelCard.ts、QdrantCard/QdrantCard.ts 等
 */

import { getAllCards } from './CardRegistry'
import { ModelCard } from './ModelCard/ModelCard'
import { QdrantCard } from './QdrantCard/QdrantCard'
import { FlaskCard } from './FlaskCard/FlaskCard'
import { DeviceCard } from './DeviceCard/DeviceCard'
import { balanceCard } from './BalanceCard/BalanceCard'

// 重新导出各卡片类型，供外部按需引用
export type { ModelBadge, ModelCardData } from './ModelCard/ModelCard'
export type { QdrantBadge, QdrantCardData } from './QdrantCard/QdrantCard'
export type { FlaskBadge, FlaskCardData } from './FlaskCard/FlaskCard'
export type { SystemInfo } from './DeviceCard/DeviceCard'

/* ==================== OverviewViewModel ==================== */
export class OverviewViewModel {
  // 卡片实例
  readonly modelCard = new ModelCard()
  readonly qdrantCard = new QdrantCard()
  readonly flaskCard = new FlaskCard()
  readonly deviceCard = new DeviceCard()
  readonly balanceCard = balanceCard

  // 从注册表获取卡片列表（用于动态渲染）
  readonly cardList = getAllCards()

  /* formatUptime：格式化运行时间
   * 流程：秒 → 天/小时/分钟 字符串
   * 示例：90s → '1分'，3665s → '1时0分'，90000s → '1天1时'
   */
  formatUptime(seconds: number): string {
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d > 0) return `${d}天${h}时`
    if (h > 0) return `${h}时${m}分`
    return `${m}分`
  }

  onMounted(): void {
    this.modelCard.start()
    this.qdrantCard.start()
    this.flaskCard.start()
    this.deviceCard.start()
    this.balanceCard.start()
  }

  onUnmounted(): void {
    this.flaskCard.cleanup()
    this.modelCard.stop()
    this.qdrantCard.stop()
    this.flaskCard.stop()
    this.deviceCard.stop()
    this.balanceCard.stop()
  }
}

export const overviewViewModel = new OverviewViewModel()
