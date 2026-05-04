/* 搜索记忆 Tab */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { Memory } from './types'

export class SearchTab {
  readonly input = ref('')
  readonly results = ref<Memory[]>([])
  readonly activeQuery = ref('')
  readonly history = ref<string[]>([])
  readonly showHistory = ref(false)
  readonly loading = ref(false)

  private _api = useApi()
  private _toast = useToast()
  private _searchTimer: ReturnType<typeof setTimeout> | null = null

  debounceSearch(): void {
    if (this._searchTimer) clearTimeout(this._searchTimer)
    this._searchTimer = setTimeout(() => this.search(), 500)
  }

  async search(): Promise<void> {
    const query = this.input.value.trim()
    if (!query) return
    if (this.loading.value) return
    this.loading.value = true
    this.activeQuery.value = query
    try {
      const r = await this._api.postJson<{ results: Memory[] }>('/memory/search', { query })
      this.results.value = r.results || []
      this.loadHistory()
    } catch {
      this._toast.show('搜索失败', 'error')
    } finally {
      this.loading.value = false
    }
  }

  searchFromHistory(query: string): void {
    this.input.value = query
    this.showHistory.value = false
    this.search()
  }

  async loadHistory(): Promise<void> {
    try {
      const r = await this._api.fetchJson<{ history: { query: string }[] }>('/memory/search-history')
      this.history.value = (r.history || []).map(h => h.query)
    } catch { /* ignore */ }
  }

  async clearHistory(): Promise<void> {
    try {
      await fetch('/memory/search-history', { method: 'DELETE' })
      this.history.value = []
    } catch { /* ignore */ }
  }

  onDocumentClick(e: MouseEvent): void {
    const wrap = document.querySelector('.search-history-wrap')
    if (wrap && !wrap.contains(e.target as Node)) this.showHistory.value = false
  }

  formatTime(ts: string): string {
    if (!ts) return ''
    try {
      return new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    } catch {
      return ts.slice(0, 16)
    }
  }
}
