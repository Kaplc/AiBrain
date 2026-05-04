/* 共享类型定义 */
export interface Memory {
  id: string
  text: string
  timestamp: string
  score?: number
}

export interface OrganizeGroup {
  group_id: number
  similarity: number
  memories: Memory[]
}

export interface RefinedItem {
  group_id: number
  original_ids: string[]
  refined_text: string
  category: string
  refined: boolean
}

/** 整理组列表项 - 每个组对应一个独立的对象实例 */
export class OrganizeGroupItem {
  /** 组 ID（列表顺序，唯一） */
  readonly groupId: number
  /** 相似度 */
  similarity: number
  /** 原始记忆列表 */
  memories: Memory[]
  /** 是否正在精炼 */
  isRefining = false
  /** 是否已精炼 */
  isRefined = false
  /** 是否已写入 */
  isApplied = false
  /** 是否正在写入（确认合并请求中） */
  isApplying = false
  /** 精炼后的文本（可编辑） */
  refinedText = ''
  /** 分类 */
  category = 'reference'
  /** 合并错误信息 */
  refineError = ''

  constructor(groupId: number, similarity: number, memories: Memory[]) {
    this.groupId = groupId
    this.similarity = similarity
    this.memories = memories
  }

  /** 触发精炼（异步，结果写入 refinedText） */
  async refine(api: { postJson: Function }): Promise<void> {
    if (this.isRefining || this.isApplied) return
    this.isRefining = true
    this.isRefined = false
    this.refineError = ''
    try {
      const r = await api.postJson<{ refined?: any[]; error?: string }>(
        '/memory/organize/refine', { groups: [this.toGroupObj()] }
      )
      if (r.error) throw new Error(r.error)
      const mapped = r.refined || []
      if (mapped.length && mapped[0]) {
        this.refinedText = mapped[0].refined_text || this.originalText()
        this.category = mapped[0].category || 'reference'
        this.isRefined = true
      }
    } catch (e: any) {
      console.error('[OrganizeGroupItem] refine failed', e)
      this.refineError = e.message || '合并失败'
    } finally {
      this.isRefining = false
    }
  }

  /** 转为传给 API 的 group 对象格式 */
  toGroupObj(): OrganizeGroup {
    return {
      group_id: this.groupId,
      similarity: this.similarity,
      memories: this.memories,
    }
  }

  /** 原始内容（多行文本） */
  originalText(): string {
    return this.memories.map((m, i) => `[${i + 1}] ${m.text}`).join('\n')
  }

  /** 当前内容（精炼后优先，否则原始拼接） */
  currentText(): string {
    return this.refinedText || this.originalText()
  }
}
