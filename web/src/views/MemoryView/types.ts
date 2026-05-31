/* 共享类型定义 - MemoryView 数据结构
 *
 * 作用：定义 MemoryView 中使用的共享类型和 OrganizeGroupItem 类
 * 包含：OrganizeGroup 接口、RefinedItem 接口、OrganizeGroupItem 类
 */
import { Memory } from './Memory'
export { Memory }

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

/* OrganizeGroupItem：整理组列表项 - 每个组对应一个独立的对象实例
 *
 * 作用：管理一组相似记忆的精炼和合并状态
 * 状态机：isRefined(是否已精炼) → isApplied(是否已应用合并) → isApplying(合并请求中)
 */
export class OrganizeGroupItem {
  // ── 基础属性 ─────────────────────────────────────────────
  /** 组 ID（列表顺序，唯一） */
  readonly groupId: number
  /** 相似度 */
  similarity: number
  /** 原始记忆列表 */
  memories: Memory[]

  // ── 状态标记 ─────────────────────────────────────────────
  /** 是否正在精炼 */
  isRefining = false
  /** 是否已精炼 */
  isRefined = false
  /** 是否已写入 */
  isApplied = false
  /** 是否正在写入（确认合并请求中） */
  isApplying = false

  // ── 精炼结果 ─────────────────────────────────────────────
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

  /* refine：触发精炼（异步，结果写入 refinedText）
   * 流程：校验状态 → POST /memory/organize/refine → 解析返回的 refined_text 和 category → 更新状态
   * 错误处理：失败时写入 refineError，isRefining 复位
   * 特殊：refined=false 且 refined_text 为空时，提示用户手动编辑
   */
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
        const item = mapped[0]
        // LLM模式关闭时，refined_text为空，提示手动编辑
        if (!item.refined && !item.refined_text) {
          // 取时间最新的原始记忆作为默认文本（最新记忆通常更完整准确）
          const sorted = [...this.memories].sort((a, b) =>
            (b.timestamp || '').localeCompare(a.timestamp || '')
          )
          const top = sorted[0]
          this.refinedText = top ? top.text : ''
          this.category = item.category || 'reference'
          this.refineError = item.hint || 'LLM模式已关闭，请手动编辑合并文本'
          this.isRefined = true
        } else {
          this.refinedText = item.refined_text || this.originalText()
          this.category = item.category || 'reference'
          this.isRefined = true
        }
      }
    } catch (e: any) {
      console.error('[OrganizeGroupItem] refine failed', e)
      this.refineError = e.message || '合并失败'
    } finally {
      this.isRefining = false
    }
  }

  /* toGroupObj：转为传给 API 的 group 对象格式 */
  toGroupObj(): OrganizeGroup {
    return {
      group_id: this.groupId,
      similarity: this.similarity,
      memories: this.memories,
    }
  }

  /* originalText：原始内容（多行文本）
   * 格式：[1] 记忆内容1\n[2] 记忆内容2
   */
  originalText(): string {
    return this.memories.map((m, i) => `[${i + 1}] ${m.text}`).join('\n')
  }

  /* currentText：当前内容（精炼后优先，否则原始拼接）
   * 优先级：refinedText → originalText()
   */
  currentText(): string {
    return this.refinedText || this.originalText()
  }
}
