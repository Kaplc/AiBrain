/* 共享类型定义 */
export interface Memory {
  id: string
  text: string
  timestamp: string
  score?: number
}

export interface OrganizeGroup {
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
