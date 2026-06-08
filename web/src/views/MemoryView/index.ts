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
import { memoryCardViewModel } from './MemoryCard/MemoryCard'

export type MemoryTab = 'search' | 'store' | 'organize' | 'settings' | 'graph' | 'entity' | 'chart'

export class MemoryViewModel {
  readonly currentTab = ref<MemoryTab>('search')
  readonly animatingCount = ref(0)

  readonly searchTab = new SearchTab()
  readonly storeTab = new StoreTab()
  readonly organizeTab = new OrganizeTab()
  readonly settingsTab = new MemorySettingsTab()
  readonly graphTab = new GraphTab()
  readonly entityTab = new EntityTab()
  readonly chartTab = memoryCardViewModel

  switchTab(tab: MemoryTab): void {
    // 离开 entity Tab 时先清理轮询
    if (this.currentTab.value === 'entity' && tab !== 'entity') {
      this.entityTab.onTabUnmounted()
    }
    this.currentTab.value = tab
    if (tab === 'store') this.storeTab.loadAll()
    if (tab === 'settings') this.settingsTab.load()
    if (tab === 'graph') this.graphTab.loadGraph()
    if (tab === 'entity') this.entityTab.onTabMounted()
    if (tab === 'chart') this.chartTab.redrawCharts()
  }

  async loadAll(): Promise<void> {
    this.storeTab.loadAll()
    this.updateStats()
  }

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

  onMounted(): void {
    console.log('[MemoryView] mounted')
    this.searchTab.loadHistory()
    this.updateStats()
    this.settingsTab.load()
    this.chartTab.onMounted()
    document.addEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }

  onUnmounted(): void {
    this.chartTab.onUnmounted()
    document.removeEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }
}

export const memoryViewModel = new MemoryViewModel()
