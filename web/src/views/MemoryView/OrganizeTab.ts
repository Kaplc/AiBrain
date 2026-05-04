/* 合并记忆 Tab - 流式分析 */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { OrganizeGroupItem } from './types'
import type { OrganizeGroup } from './types'
import { memoryViewModel } from './index'

export class OrganizeTab {
  readonly groups = ref<OrganizeGroupItem[]>([])
  readonly busy = ref(false)
  readonly threshold = ref('0.85')

  private _api = useApi()
  private _toast = useToast()
  private _abortController: AbortController | null = null

  get unrefinedCount(): number {
    return this.groups.value.filter(g => !g.isRefined && !g.isApplied).length
  }

  async start(): Promise<void> {
    if (this.busy.value) return
    this.busy.value = true

    // 重置状态
    this.groups.value = []

    const sim = parseFloat(this.threshold.value) || 0.85
    this._abortController = new AbortController()

    try {
      const response = await fetch('/memory/organize/dedup/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ similarity_threshold: sim }),
        signal: this._abortController.signal,
      })

      if (!response.ok) throw new Error('HTTP ' + response.status)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const msg = JSON.parse(line.slice(6))
            if (msg.type === 'batch') {
              // 追加新发现的组到列表末尾
              if (msg.groups && msg.groups.length) {
                const startId = this.groups.value.length
                const newItems = (msg.groups as OrganizeGroup[]).map(
                  (g, i) => new OrganizeGroupItem(startId + i, g.similarity, g.memories)
                )
                this.groups.value = [...this.groups.value, ...newItems]
              }
            } else if (msg.type === 'done') {
              this.busy.value = false
              if (!msg.groups || !msg.groups.length) {
                this._toast.show('没有发现重复的记忆（共 ' + (msg.total || 0) + ' 条）')
              } else {
                this._toast.show('分析完成，共发现 ' + msg.groups.length + ' 组重复记忆')
              }
            } else if (msg.type === 'error') {
              this.busy.value = false
              this._toast.show('分析异常: ' + msg.error, 'error')
            }
          } catch {}
        }
      }

      this.busy.value = false
    } catch (e: any) {
      if (e.name === 'AbortError') {
        // 主动停止
      } else {
        console.error('[OrganizeTab] stream error', e)
        this._toast.show('流式分析连接失败', 'error')
        this.busy.value = false
      }
    } finally {
      this._abortController = null
    }
  }

  async refineGroup(groupId: number): Promise<void> {
    const g = this.groups.value.find(x => x.groupId === groupId)
    if (!g || g.isApplied) return
    // 重新精炼：重置状态
    g.isRefined = false
    g.refinedText = ''
    g.category = 'reference'
    g.refineError = ''
    await g.refine(this._api)
    if (g.isRefined) {
      this._toast.show('组 ' + (groupId + 1) + ' 合并完成')
    }
  }

  async applySingle(groupId: number): Promise<void> {
    const g = this.groups.value.find(x => x.groupId === groupId)
    if (!g || g.isApplied || g.isApplying) return
    const newText = g.currentText().trim()
    if (!newText) { this._toast.show('内容为空', 'error'); return }
    g.isApplying = true
    try {
      const r = await this._api.postJson<{ error?: string }>('/memory/organize/apply', {
        items: [{ delete_ids: g.memories.map(m => m.id), new_text: newText, category: g.category }]
      })
      if (r.error) { this._toast.show('写入失败: ' + r.error, 'error'); return }
      this._toast.show('已合并该组记忆（删除 ' + g.memories.length + ' 条，新增 1 条）')
      g.isApplied = true
      memoryViewModel.updateStats()
    } catch (e: any) {
      this._toast.show('写入失败: ' + e.message, 'error')
    } finally {
      g.isApplying = false
    }
  }
}
