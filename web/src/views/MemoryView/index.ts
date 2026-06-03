/* 记忆视图模型 - 组合各 Tab 类
 *
 * 作用：作为 MemoryView 的顶层 ViewModel，管理 SearchTab/StoreTab/OrganizeTab/SettingsTab 四个子模块
 * 实现：提供 Tab 切换、统计更新、动画数字等通用功能，各 Tab 独立维护自己的状态
 */

import { ref } from 'vue'
import { SearchTab } from './SearchTab/SearchTab'
import { StoreTab } from './StoreTab/StoreTab'
import { OrganizeTab } from './OrganizeTab/OrganizeTab'
import { MemorySettingsTab } from './SettingsTab/MemorySettingsTab'
import { GraphTab } from './GraphTab/GraphTab'
import { EntityTab } from './EntityTab/EntityTab'

export class MemoryViewModel {
  readonly currentTab = ref<'search' | 'store' | 'organize' | 'settings' | 'graph' | 'entity'>('search')
  readonly animatingCount = ref(0)

  readonly searchTab = new SearchTab()
  readonly storeTab = new StoreTab()
  readonly organizeTab = new OrganizeTab()
  readonly settingsTab = new MemorySettingsTab()
  readonly graphTab = new GraphTab()
  readonly entityTab = new EntityTab()

  /* switchTab：切换 Tab
   * 流程：更新 currentTab → 如果切换到 store Tab 则加载记忆列表 → 切换到 settings 则加载设置
   */
  switchTab(tab: 'search' | 'store' | 'organize' | 'settings' | 'graph' | 'entity'): void {
    // 离开 entity Tab 时先清理轮询
    if (this.currentTab.value === 'entity' && tab !== 'entity') {
      this.entityTab.onTabUnmounted()
    }
    this.currentTab.value = tab
    if (tab === 'store') this.storeTab.loadAll()
    if (tab === 'settings') this.settingsTab.load()
    if (tab === 'graph') this.graphTab.loadGraph()
    if (tab === 'entity') this.entityTab.onTabMounted()
  }

  /* loadAll：加载所有数据（初始化时调用）
   * 流程：加载 store Tab 记忆列表 → 更新统计
   */
  async loadAll(): Promise<void> {
    this.storeTab.loadAll()
    this.updateStats()
  }

  /* updateStats：从后端获取记忆总数并触发动画
   * 流程：GET /memory/count → animateCount 动画过渡到目标数字
   * 错误处理：失败时使用本地 storeTab.memories 数量作为兜底
   */
  async updateStats(): Promise<void> {
    const { useApi } = await import('@/composables/useApi')
    const api = useApi()
    try {
      const r = await api.fetchJson<{ count: number }>('/memory/count')
      this.animateCount(r.count || 0)
    } catch {
      this.animatingCount.value = this.storeTab.memories.value.length
    }
  }

  /* animateCount：数字动画过渡效果
   * 流程：计算起始值和目标值的差 → 每 50ms 递增步进值 → 接近目标时直接跳到目标值
   * 步进策略：差值/10，最小为 1，保证动画流畅且不过于缓慢
   */
  animateCount(target: number): void {
    const current = this.animatingCount.value
    if (current === target) return
    const diff = target - current
    const step = Math.max(1, Math.ceil(Math.abs(diff) / 10))
    const iv = setInterval(() => {
      const now = this.animatingCount.value
      const delta = target > now ? Math.min(step, target - now) : Math.max(-step, target - now)
      if (now === target || (delta > 0 ? now >= target : now <= target)) {
        this.animatingCount.value = target
        clearInterval(iv)
      } else {
        this.animatingCount.value = now + delta
      }
    }, 50)
  }

  /* onMounted：组件挂载时的初始化
   * 流程：加载搜索历史 → 更新统计 → 加载记忆设置 → 挂载文档点击事件监听（关闭历史面板）
   */
  onMounted(): void {
    console.log('[MemoryView] mounted')
    this.searchTab.loadHistory()
    this.updateStats()
    this.settingsTab.load()
    document.addEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }

  /* onUnmounted：组件卸载时清理
   * 流程：移除文档点击事件监听，防止内存泄漏
   */
  onUnmounted(): void {
    document.removeEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }
}

export const memoryViewModel = new MemoryViewModel()
