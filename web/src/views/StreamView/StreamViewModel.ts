/* 记忆流视图模型 - 面向对象设计 */

import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'

/* ==================== Types ==================== */
export interface StreamItem {
  id: number
  action: 'store' | 'search' | 'delete'
  content: string
  memory_id: string | null
  status: 'pending' | 'done' | 'error' | ''
  created_at: string
}

export interface StreamResponse {
  items: StreamItem[]
  total: number
}

/* ==================== SteamViewModel ==================== */
export class StreamViewModel {
  // State
  readonly storeItems = ref<StreamItem[]>([])
  readonly searchItems = ref<StreamItem[]>([])
  readonly storeTotal = ref(0)
  readonly searchTotal = ref(0)
  readonly knownIds = ref(new Set<string>())

  // Computed
  readonly totalCount = computed(() =>
    `MCP ${this.storeTotal.value} 条 / 搜索 ${this.searchTotal.value} 条`
  )
  readonly storeCountText = computed(() => `${this.storeItems.value.length} 条`)
  readonly searchCountText = computed(() => `${this.searchItems.value.length} 条`)

  // Private
  private _api = useApi()
  private _statusPoll = usePolling(() => this.pollStatus(), 1000)
  private _streamPoll = usePolling(() => this.loadStream(), 2000)

  /* ==================== Helpers ==================== */
  getActionLabel(action: string): string {
    if (action === 'store') return '存入'
    if (action === 'search') return '搜索'
    return '删除'
  }

  formatTime(createdAt: string): string {
    return (createdAt || '').slice(11, 19)
  }

  getItemText(item: StreamItem): string {
    return item.content || item.memory_id || ''
  }

  isNew(id: number): boolean {
    return !this.knownIds.value.has(String(id))
  }

  markKnown(items: StreamItem[]): void {
    items.forEach(item => this.knownIds.value.add(String(item.id)))
  }

  getStatusIcon(status: string): 'pending' | 'done' | 'error' | '' {
    if (status === 'pending') return 'pending'
    if (status === 'done') return 'done'
    if (status === 'error') return 'error'
    return ''
  }

  /* ==================== Load stream ==================== */
  async loadStream(): Promise<void> {
    try {
      const [storeRes, searchRes] = await Promise.all([
        this._api.fetchJson<StreamResponse>('/stream/api?action=store&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=search&days=3'),
      ])

      this.storeItems.value = storeRes.items || []
      this.searchItems.value = searchRes.items || []
      this.storeTotal.value = storeRes.total || 0
      this.searchTotal.value = searchRes.total || 0

      requestAnimationFrame(() => {
        this.markKnown(this.storeItems.value)
        this.markKnown(this.searchItems.value)
      })
    } catch (e) {
      console.error('[SteamView] load failed:', e)
    }
  }

  /* ==================== Status poll ==================== */
  async pollStatus(): Promise<void> {
    const allCurrent = [...this.storeItems.value, ...this.searchItems.value]
    const hasPending = allCurrent.some(i => i.status === 'pending')
    if (!hasPending) return

    try {
      const [storeRes, searchRes] = await Promise.all([
        this._api.fetchJson<StreamResponse>('/stream/api?action=store&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=search&days=3'),
      ])

      const allFresh = [
        ...(storeRes.items || []),
        ...(searchRes.items || []),
      ]
      const statusMap = new Map<number, string>()
      allFresh.forEach(i => statusMap.set(i.id, i.status))

      const updateStatus = (items: StreamItem[]) => {
        for (let i = 0; i < items.length; i++) {
          const item = items[i]
          if (item.status === 'pending') {
            const newStatus = statusMap.get(item.id)
            if (newStatus && newStatus !== 'pending') {
              items[i] = { ...item, status: newStatus as StreamItem['status'] }
            }
          }
        }
      }

      this.storeItems.value = [...this.storeItems.value]
      this.searchItems.value = [...this.searchItems.value]
      updateStatus(this.storeItems.value)
      updateStatus(this.searchItems.value)
    } catch {
      // silent
    }
  }

  /* ==================== Lifecycle ==================== */
  onMounted(): void {
    console.log('[SteamView] mounted')
    this.loadStream()
    this._streamPoll.start()
    this._statusPoll.start()
  }

  onUnmounted(): void {
    this._streamPoll.stop()
    this._statusPoll.stop()
  }
}

// 单例
export const streamViewModel = new StreamViewModel()