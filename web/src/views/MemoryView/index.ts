/* 记忆视图模型 - 组合各 Tab 类 */

import { ref } from 'vue'
import { SearchTab } from './SearchTab'
import { StoreTab } from './StoreTab'
import { OrganizeTab } from './OrganizeTab'

export class MemoryViewModel {
  readonly currentTab = ref<'search' | 'store' | 'organize'>('search')
  readonly animatingCount = ref(0)

  readonly searchTab = new SearchTab()
  readonly storeTab = new StoreTab()
  readonly organizeTab = new OrganizeTab()

  switchTab(tab: 'search' | 'store' | 'organize'): void {
    this.currentTab.value = tab
    if (tab === 'store') this.storeTab.loadAll()
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
    document.addEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }

  onUnmounted(): void {
    document.removeEventListener('click', this.searchTab.onDocumentClick.bind(this.searchTab))
  }
}

export const memoryViewModel = new MemoryViewModel()
