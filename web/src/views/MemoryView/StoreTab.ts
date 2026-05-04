/* 保存记忆 Tab */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { Memory } from './types'

export class StoreTab {
  readonly input = ref('')
  readonly memories = ref<Memory[]>([])

  private _api = useApi()
  private _toast = useToast()

  formatTime(ts: string): string {
    if (!ts) return ''
    try {
      return new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    } catch {
      return ts.slice(0, 16)
    }
  }

  async loadAll(): Promise<void> {
    try {
      const r = await this._api.postJson<{ memories: Memory[] }>('/memory/list', { source: 'user' })
      this.memories.value = r.memories || []
    } catch (e) {
      console.error('[memory] loadAll error:', e)
    }
  }

  async save(): Promise<void> {
    const text = this.input.value.trim()
    if (!text) return
    try {
      // 用户保存的记忆，标记 source: user
      const r = await this._api.postJson<{ result?: string; error?: string }>('/memory/store', { text, memory_meta: { source: 'user' } })
      if (r.error) { this._toast.show(r.error, 'error'); return }
      this._toast.show(r.result || '保存成功')
      this.input.value = ''
      this.loadAll()
    } catch {
      this._toast.show('连接失败', 'error')
    }
  }

  async delete(id: string): Promise<void> {
    try {
      const r = await this._api.postJson<{ result?: string; error?: string }>('/memory/delete', { memory_id: id })
      if (r.error) { this._toast.show(r.error, 'error'); return }
      this._toast.show(r.result || '删除成功')
      this.memories.value = this.memories.value.filter(m => m.id !== id)
    } catch {
      this._toast.show('删除失败', 'error')
    }
  }
}
