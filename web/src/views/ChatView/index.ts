/* ChatView ViewModel — 单会话聊天 + SSE 流式消费
 *
 * 职责：
 * - 消息列表管理（加载历史、追加新消息）
 * - SSE 流式 token 拼接（shallowRef 优化）
 * - AbortController 取消
 * - 意识流状态轮询
 */
import { reactive, ref, shallowRef, onMounted, onUnmounted, nextTick } from 'vue'
import { useToast } from '@/composables/useToast'

export interface ChatMessage {
  id?: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  is_thought?: number
  isStreaming?: boolean
  created_at?: string
}

const API_BASE = window.location.origin

export class ChatViewModel {
  messages = reactive<ChatMessage[]>([])
  sending = ref(false)
  currentStatus = ref('')
  loopState = reactive({
    is_running: false,
    idle_enabled: false,
    idle_interval_seconds: 45,
    idle_count: 0,
    last_thought_at: null as number | null,
    last_thought_preview: null as string | null,
    is_busy: false,
    consecutive_failures: 0,
    current_status: '',
    prompt_tokens: 0,
    completion_tokens: 0,
    max_context_tokens: 400000,
    // 大脑循环状态（来自 /chat/state brain 字段）
    brain: null as {
      life_loop_status: string
      current_activity: string
      current_focus: string
      idle_seconds: number
      energy: number
      mood: { label?: string; valence?: number; arousal?: number }
      open_loop_count: number
      pending_expression_count: number
      scheduler_running: boolean
      drives: Record<string, number>
      top_concerns: Array<{ node_id: string; effective: number }>
      reflection: {
        last_reflection_at: string | null
        last_reflection_summary: string
        beliefs: string[]
        interests: string[]
        goals: string[]
        open_questions: string[]
      }
      last_error: string
    } | null,
  })

  private _pollTimer: ReturnType<typeof setInterval> | null = null
  private _pollMsgTimer: ReturnType<typeof setInterval> | null = null
  private _toast = useToast()
  private _scrollFn: (() => void) | null = null
  private _evtSource: EventSource | null = null
  private _typewriterTimer: ReturnType<typeof setInterval> | null = null

  /* setScrollFn：由 Vue 组件注入 scrollToBottom 方法 */
  setScrollFn(fn: () => void) {
    this._scrollFn = fn
  }

  private _scrollToBottom() {
    nextTick(() => this._scrollFn?.())
  }

  /* loadMessages：从工作记忆加载持久化对话历史 */
  async loadMessages(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/chat/history`)
      const data = await resp.json()
      if (data.messages) {
        this.messages.splice(0, this.messages.length)
        for (const m of data.messages) {
          this.messages.push({
            role: m.role,
            content: m.content,
            created_at: m.created_at,
            isStreaming: false,
          })
        }
        this._scrollToBottom()
      }
    } catch (e) {
      console.error('[chat] load messages failed:', e)
    }
  }

  /* loadState：加载意识流状态 + 当前处理状态 */
  async loadState(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/chat/state`)
      const data = await resp.json()
      Object.assign(this.loopState, data)
      if (data.current_status) {
        this.currentStatus.value = data.current_status
      }
    } catch (e) {
      console.error('[chat] load state failed:', e)
    }
  }

  /* startStatePolling：开启状态轮询（每 10s） + 消息轮询（每 30s） */
  startStatePolling(): void {
    this.loadState()
    this._pollTimer = setInterval(() => this.loadState(), 10000)
    // 后台主动消息轮询——只在非 streaming 时刷新，避免冲掉流式回复
    this._pollMsgTimer = setInterval(() => this._reloadIfIdle(), 30000)
    this.startEventStream()
  }

  private async _loadMessagesSilent(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/chat/history`)
      const data = await resp.json()
      if (!data.messages) return
      // 只在消息条数或最后一条内容有变化时才更新
      const last = data.messages[data.messages.length - 1]
      const myLast = this.messages[this.messages.length - 1]
      if (data.messages.length === this.messages.length &&
          last?.content === myLast?.content) return
      // 记录刷新前最后一条 assistant 内容，用于判断哪条是"新增"需打字机
      const prevLastAssistant = [...this.messages].reverse().find(m => m.role === 'assistant')?.content
      this.messages.splice(0, this.messages.length)
      for (const m of data.messages) {
        this.messages.push({
          role: m.role,
          content: m.content,
          created_at: m.created_at,
          isStreaming: false,
        })
      }
      // 新增的最后一条 assistant → 本地打字机动画（收到后才逐字出现）
      const newLastAssistant = [...this.messages].reverse().find(m => m.role === 'assistant')
      if (newLastAssistant && newLastAssistant.content &&
          newLastAssistant.content !== prevLastAssistant) {
        this._typewriter(newLastAssistant)
      }
      this._scrollToBottom()
    } catch {
      // 静默失败
    }
  }

  /* stopStatePolling：停止所有轮询 */
  stopStatePolling(): void {
    if (this._pollTimer) {
      clearInterval(this._pollTimer)
      this._pollTimer = null
    }
    if (this._pollMsgTimer) {
      clearInterval(this._pollMsgTimer)
      this._pollMsgTimer = null
    }
    if (this._typewriterTimer) {
      clearInterval(this._typewriterTimer)
      this._typewriterTimer = null
    }
    this.stopEventStream()
  }

  /* startEventStream：订阅 /brain/events/stream，收到 workmemory/new_message 立即刷新 */
  startEventStream(): void {
    if (this._evtSource) return
    if (typeof EventSource === 'undefined') return  // 环境不支持则静默退化到轮询
    const es = new EventSource(`${API_BASE}/brain/events/stream`)
    es.addEventListener('brain_event', (ev) => {
      try {
        const payload = JSON.parse((ev as MessageEvent).data)
        if (payload.source === 'workmemory' && payload.type === 'new_message') {
          this._reloadIfIdle()
        }
      } catch {
        // 静默
      }
    })
    es.onerror = () => {
      // EventSource 会自动重连，这里不手动 close
    }
    this._evtSource = es
  }

  /* stopEventStream：关闭 SSE 连接 */
  stopEventStream(): void {
    if (this._evtSource) {
      this._evtSource.close()
      this._evtSource = null
    }
  }

  /* _reloadIfIdle：末条正在流式则跳过（避免冲掉流式占位），否则静默刷新 */
  private async _reloadIfIdle(): Promise<void> {
    if (this.messages.length > 0 && this.messages[this.messages.length - 1].isStreaming) {
      return
    }
    await this._loadMessagesSilent()
  }

  /* triggerProactive：触发猫猫主动消息 */
  async triggerProactive(): Promise<void> {
    try {
      await fetch(`${API_BASE}/chat/proactive`, { method: 'POST' })
      // 触发后立即刷新消息列表（轮询 30s 间隔太长）
      await this._loadMessagesSilent()
    } catch (e) {
      console.error('[chat] proactive trigger failed:', e)
    }
  }

  /* sendMessage：发送消息（后端写盘 + 入队，回复经 EventSource 刷新 + 本地打字机显示） */
  async sendMessage(text: string): Promise<void> {
    if (!text.trim() || this.sending.value) return

    // 追加用户消息（乐观显示，后端写盘后 EventSource 刷新确认）
    const _ts = new Date()
    const _tsStr = `${_ts.getFullYear()}-${String(_ts.getMonth()+1).padStart(2,'0')}-${String(_ts.getDate()).padStart(2,'0')} ${String(_ts.getHours()).padStart(2,'0')}:${String(_ts.getMinutes()).padStart(2,'0')}:${String(_ts.getSeconds()).padStart(2,'0')}`
    this.messages.push({ role: 'user', content: text, created_at: _tsStr })
    this._scrollToBottom()
    this.sending.value = true

    try {
      const resp = await fetch(`${API_BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (resp.status === 503) {
        const data = await resp.json()
        this._toast.show(data.message || '请先配置 Chat', 'error')
        return
      }
      if (!resp.ok) {
        this._toast.show(`请求失败 ${resp.status}`, 'error')
        return
      }
      // 发送成功：用户消息已由后端写盘 + emit，猫猫回复经 EventSource 实时刷新 + 打字机显示
    } catch (e: any) {
      this._toast.show(String(e), 'error')
    } finally {
      this.sending.value = false
    }
  }

  /* _typewriter：对一条已收到的完整消息做本地逐字打字机效果（收到后才动画，假表象） */
  private _typewriter(msg: ChatMessage): void {
    if (!msg.content || msg.isStreaming) return
    if (this._typewriterTimer) { clearInterval(this._typewriterTimer); this._typewriterTimer = null }
    const full = msg.content
    msg.content = ''
    msg.isStreaming = true
    const step = Math.max(1, Math.ceil(full.length / 50))  // 约 1.5 秒打完
    let i = 0
    this._typewriterTimer = setInterval(() => {
      i += step
      if (i >= full.length) {
        msg.content = full
        msg.isStreaming = false
        if (this._typewriterTimer) { clearInterval(this._typewriterTimer); this._typewriterTimer = null }
      } else {
        msg.content = full.slice(0, i)
      }
      this._scrollToBottom()
    }, 30)
  }


  /* clearChat：清空对话 */
  async clearChat(): Promise<void> {
    try {
      await fetch(`${API_BASE}/chat/clear`, { method: 'POST' })
      this.messages.splice(0, this.messages.length)
      this._toast.show('对话已清空', 'info')
    } catch (e) {
      this._toast.show('清空失败', 'error')
    }
  }
}

// 单例导出
export const chatViewModel = new ChatViewModel()
