/* 整理记忆 Tab */
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { OrganizeGroup, RefinedItem } from './types'

export class OrganizeTab {
  readonly groups = ref<OrganizeGroup[]>([])
  readonly refined = ref<RefinedItem[]>([])
  readonly busy = ref(false)
  readonly appliedIds = ref<number[]>([])
  readonly threshold = ref('0.85')

  private _api = useApi()
  private _toast = useToast()

  get unrefinedCount(): number {
    let c = 0
    for (let i = 0; i < this.groups.value.length; i++) {
      if (!this.refined.value.some(r => r.group_id === i)) c++
    }
    return c
  }

  async start(): Promise<void> {
    if (this.busy.value) return
    this.busy.value = true
    const sim = parseFloat(this.threshold.value) || 0.85
    try {
      const r = await this._api.postJson<{
        groups: OrganizeGroup[]
        total_memories: number
        grouped_count: number
        error?: string
      }>('/memory/organize/dedup', { similarity_threshold: sim })
      if (r.error) { this._toast.show(r.error, 'error'); this.busy.value = false; return }
      this.groups.value = r.groups || []
      this.refined.value = []
      this.appliedIds.value = []
      if (!this.groups.value.length) {
        this._toast.show('没有发现重复的记忆（共 ' + (r.total_memories || 0) + ' 条）')
      }
    } catch (e: any) {
      this._toast.show('请求失败: ' + e.message, 'error')
    } finally {
      this.busy.value = false
    }
  }

  async refineGroup(idx: number): Promise<void> {
    if (!this.groups.value[idx]) return
    if (this.refined.value.some(r => r.group_id === idx)) {
      this._toast.show('该组已精炼', 'info'); return
    }
    try {
      const r = await this._api.postJson<{ refined: RefinedItem[]; error?: string }>(
        '/memory/organize/refine', { groups: [this.groups.value[idx]] }
      )
      if (r.error) { this._toast.show('精炼失败: ' + r.error, 'error'); return }
      const mapped = (r.refined || []).map(item => ({ ...item, group_id: idx }))
      this.refined.value = [...this.refined.value, ...mapped]
    } catch (e: any) {
      this._toast.show('精炼失败: ' + e.message, 'error')
    }
  }

  refineAll(): void {
    if (!this.groups.value.length) return
    const unrefined: number[] = []
    for (let i = 0; i < this.groups.value.length; i++) {
      if (!this.refined.value.some(r => r.group_id === i)) unrefined.push(i)
    }
    if (!unrefined.length) { this._toast.show('所有组已精炼', 'info'); return }
    unrefined.forEach(i => this.refineGroup(i))
  }

  isApplied(gi: number): boolean { return this.appliedIds.value.includes(gi) }
  isRefined(gi: number): boolean { return this.refined.value.some(r => r.group_id === gi) }

  async applySingle(groupId: number): Promise<void> {
    const idx = this.refined.value.findIndex(r => r.group_id === groupId)
    if (idx === -1) return
    const item = this.refined.value[idx]
    const el = document.getElementById('refinedText' + groupId)
    const newText = el ? (el as HTMLElement).innerText.trim() : item.refined_text
    if (!newText) { this._toast.show('精炼内容为空', 'error'); return }
    try {
      const r = await this._api.postJson<{ error?: string }>('/memory/organize/apply', {
        items: [{ delete_ids: item.original_ids, new_text: newText, category: item.category || 'reference' }]
      })
      if (r.error) { this._toast.show('写入失败: ' + r.error, 'error'); return }
      this._toast.show('已合并该组记忆（删除 ' + item.original_ids.length + ' 条，新增 1 条）')
      this.refined.value = this.refined.value.filter((_, i) => i !== idx)
      if (!this.appliedIds.value.includes(groupId)) this.appliedIds.value.push(groupId)
      if (!this.refined.value.length && this.groups.value.length &&
          this.appliedIds.value.length === this.groups.value.length) {
        this.groups.value = []
        this.refined.value = []
        this.appliedIds.value = []
      }
    } catch (e: any) {
      this._toast.show('写入失败: ' + e.message, 'error')
    }
  }

  async applyAll(): Promise<void> {
    if (!this.refined.value.length) return
    const items: { delete_ids: string[]; new_text: string; category: string }[] = []
    for (let i = 0; i < this.refined.value.length; i++) {
      const item = this.refined.value[i]
      const check = document.getElementById('refinedCheck' + item.group_id) as HTMLInputElement
      if (!check || !check.checked) continue
      const el = document.getElementById('refinedText' + item.group_id)
      const newText = el ? (el as HTMLElement).innerText.trim() : item.refined_text
      if (!newText) continue
      items.push({ delete_ids: item.original_ids, new_text: newText, category: item.category || 'reference' })
    }
    if (!items.length) { this._toast.show('没有勾选任何项', 'error'); return }
    try {
      const r = await this._api.postJson<{ applied: number; deleted: number; added: number; error?: string }>('/memory/organize/apply', { items })
      if (r.error) { this._toast.show('写入失败: ' + r.error, 'error'); return }
      this._toast.show('已合并 ' + r.applied + ' 组记忆（删除 ' + r.deleted + ' 条，新增 ' + r.added + ' 条）')
      this.groups.value = []
      this.refined.value = []
      this.appliedIds.value = []
    } catch (e: any) {
      this._toast.show('写入失败: ' + e.message, 'error')
    }
  }
}
