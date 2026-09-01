/* 单条记忆数据模型（移植自 Vue 版 Memory.ts） */
export interface MemoryRaw {
  id: string
  text: string
  timestamp: string
  score?: number
  category?: string
}

export class Memory {
  readonly id: string
  readonly text: string
  readonly timestamp: string
  readonly score?: number
  readonly category?: string

  constructor(data: MemoryRaw) {
    this.id = data.id
    this.text = data.text
    this.timestamp = data.timestamp
    this.score = data.score
    this.category = data.category
  }

  get categoryLabel(): string {
    const map: Record<string, string> = { life: 'life', fact: '事实', exp: '经验' }
    return this.category ? map[this.category] || this.category : ''
  }

  get scorePercent(): string {
    return this.score !== undefined ? `${(this.score * 100).toFixed(1)}%` : ''
  }

  get formattedTime(): string {
    if (!this.timestamp) return ''
    try {
      return new Date(this.timestamp).toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      })
    } catch {
      return this.timestamp.slice(0, 16)
    }
  }

  get shortId(): string {
    return this.id.slice(0, 8)
  }
}
