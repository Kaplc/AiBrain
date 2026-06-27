/* 记忆流视图模型（协调器）
 *
 * 作用：顶层协调器，管理 3 种流的轮询与 knownIds 动画
 *       同时提供保存/搜索/删除长时记忆的交互操作方法
 * 依赖：StoreStream / SearchStream / DeleteStream（各自独立文件）
 */

import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { usePolling } from '@/composables/usePolling'
import { useToast } from '@/composables/useToast'
import type { StreamResponse, StreamItemData } from './types'
import type { StreamItemBase } from './StreamItemBase'
import { StoreStream } from './StoreStream'
import { SearchStream } from './SearchStream'
import { DeleteStream } from './DeleteStream'

export type { StreamItemData, StreamResponse } from './types'
export { StoreStream } from './StoreStream'
export { SearchStream } from './SearchStream'
export { DeleteStream } from './DeleteStream'
export { StoreStreamItem } from './StoreStreamItem'
export { SearchStreamItem } from './SearchStreamItem'
export { DeleteStreamItem } from './DeleteStreamItem'

/** 搜索结果条目 */
export interface MemorySearchResult {
  memory_id: string
  text: string
  score: number
  source: string
  created_at: string
}

export class StreamViewModel {
  // 3种流实例
  readonly storeStream = new StoreStream()
  readonly searchStream = new SearchStream()
  readonly deleteStream = new DeleteStream()

  // 供模板 v-for 统一渲染
  readonly streams = [this.storeStream, this.searchStream, this.deleteStream]

  // 新出现项的 ID 集合（用于入场动画）
  readonly knownIds = ref(new Set<string>())

  // 顶部汇总文字
  readonly totalCount = computed(() =>
    `MCP ${this.storeStream.total.value} 条 / 搜索 ${this.searchStream.total.value} 条 / 删除 ${this.deleteStream.total.value} 条`
  )

  // ── 操作状态 ──

  /** 保存输入文本 */
  readonly storeInput = ref('')
  readonly storeLoading = ref(false)

  /** 搜索输入 */
  readonly searchInput = ref('')
  readonly searchLoading = ref(false)
  readonly searchResults = ref<MemorySearchResult[]>([])
  readonly searchShowResults = ref(false)

  /** 删除输入 */
  readonly deleteInput = ref('')
  readonly deleteLoading = ref(false)

  // Private
  private _api = useApi()
  private _toast = useToast()
  private _statusPoll = usePolling(() => this.pollStatus(), 1000)
  private _streamPoll = usePolling(() => this.loadStream(), 2000)

  /* isNew：判断是否为新出现的项（用于触发动画） */
  isNew(id: number): boolean {
    return !this.knownIds.value.has(String(id))
  }

  private markKnown(items: StreamItemBase[]): void {
    items.forEach(item => this.knownIds.value.add(String(item.id)))
  }

  /* loadStream：并行拉取 3 种操作流 */
  async loadStream(): Promise<void> {
    try {
      const [storeRes, searchRes, deleteRes] = await Promise.all([
        this._api.fetchJson<StreamResponse>('/stream/api?action=store&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=search&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=delete&days=3'),
      ])
      this.storeStream.load(storeRes)
      this.searchStream.load(searchRes)
      this.deleteStream.load(deleteRes)

      requestAnimationFrame(() => {
        this.markKnown(this.storeStream.items.value)
        this.markKnown(this.searchStream.items.value)
        this.markKnown(this.deleteStream.items.value)
      })
    } catch (e) {
      console.error('[StreamView] load failed:', e)
    }
  }

  /* pollStatus：轮询更新 pending 状态 */
  async pollStatus(): Promise<void> {
    const allItems = [
      ...this.storeStream.items.value,
      ...this.searchStream.items.value,
      ...this.deleteStream.items.value,
    ]
    if (!allItems.some(i => i.status === 'pending')) return

    try {
      const [storeRes, searchRes, deleteRes] = await Promise.all([
        this._api.fetchJson<StreamResponse>('/stream/api?action=store&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=search&days=3'),
        this._api.fetchJson<StreamResponse>('/stream/api?action=delete&days=3'),
      ])

      const statusMap = new Map<number, StreamItemData['status']>()
      ;[...storeRes.items, ...searchRes.items, ...deleteRes.items]
        .forEach(i => statusMap.set(i.id, i.status))

      this.storeStream.applyStatusMap(statusMap)
      this.searchStream.applyStatusMap(statusMap)
      this.deleteStream.applyStatusMap(statusMap)
    } catch {
      // silent
    }
  }

  /* ── 交互操作方法 ── */

  /** 保存文本到长时记忆 */
  async storeMemory(): Promise<void> {
    const text = this.storeInput.value.trim()
    if (!text) return
    this.storeLoading.value = true
    try {
      await this._api.postJson<any>('/memory/store', { text })
      this.storeInput.value = ''
      this._toast.show('记忆已保存', 'success')
      // 刷新流以看到新条目
      setTimeout(() => this.loadStream(), 600)
    } catch (e: any) {
      this._toast.show('保存失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      this.storeLoading.value = false
    }
  }

  /** 搜索长时记忆 */
  async searchMemory(): Promise<void> {
    const query = this.searchInput.value.trim()
    if (!query) return
    this.searchLoading.value = true
    this.searchResults.value = []
    this.searchShowResults.value = true
    try {
      const res = await this._api.postJson<{ results: any[] }>('/memory/search', { query })
      this.searchResults.value = (res.results || []).map((r: any) => ({
        memory_id: r.id || r.memory_id || '',
        text: r.text || r.content || '',
        score: r.score || 0,
        source: r.source || '',
        created_at: r.created_at || r.timestamp || '',
      }))
    } catch (e: any) {
      this._toast.show('搜索失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      this.searchLoading.value = false
    }
  }

  /** 关闭搜索结果 */
  closeSearchResults(): void {
    this.searchShowResults.value = false
    this.searchResults.value = []
  }

  /** 按 memory_id 删除长时记忆 */
  async deleteMemory(memoryId?: string): Promise<void> {
    const id = (memoryId || this.deleteInput.value).trim()
    if (!id) return
    this.deleteLoading.value = true
    try {
      await this._api.postJson<any>('/memory/delete', { memory_id: id })
      this.deleteInput.value = ''
      this._toast.show('记忆已删除', 'success')
      setTimeout(() => this.loadStream(), 600)
    } catch (e: any) {
      this._toast.show('删除失败: ' + (e.message || '未知错误'), 'error')
    } finally {
      this.deleteLoading.value = false
    }
  }

  /* 生命周期 */
  onMounted(): void {
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
