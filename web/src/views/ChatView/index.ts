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
  role: 'user' | 'assistant' | 'system'
  content: string
  is_thought?: number
  isStreaming?: boolean
  created_at?: string
}

const API_BASE = window.location.origin

export class ChatViewModel {
  messages = reactive<ChatMessage[]>([])
  sending = ref(false)
  loopState = reactive({
    is_running: false,
    idle_enabled: false,
    idle_interval_seconds: 45,
    idle_count: 0,
    last_thought_at: null as number | null,
    last_thought_preview: null as string | null,
    is_busy: false,
    consecutive_failures: 0,
  })

  private _abortCtl: AbortController | null = null
  private _pollTimer: ReturnType<typeof setInterval> | null = null
  private _toast = useToast()
  private _scrollFn: (() => void) | null = null

  /* setScrollFn：由 Vue 组件注入 scrollToBottom 方法 */
  setScrollFn(fn: () => void) {
    this._scrollFn = fn
  }

  private _scrollToBottom() {
    nextTick(() => this._scrollFn?.())
  }

  /* loadMessages：加载历史消息 */
  async loadMessages(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/chat/messages`)
      const data = await resp.json()
      if (data.messages) {
        this.messages.splice(0, this.messages.length)
        for (const m of data.messages) {
          this.messages.push({ ...m, isStreaming: false })
        }
        this._scrollToBottom()
      }
    } catch (e) {
      console.error('[chat] load messages failed:', e)
    }
  }

  /* loadState：加载意识流状态 */
  async loadState(): Promise<void> {
    try {
      const resp = await fetch(`${API_BASE}/chat/state`)
      const data = await resp.json()
      Object.assign(this.loopState, data)
    } catch (e) {
      console.error('[chat] load state failed:', e)
    }
  }

  /* startStatePolling：开启状态轮询（每 10s） */
  startStatePolling(): void {
    this.loadState()
    this._pollTimer = setInterval(() => this.loadState(), 10000)
  }

  /* stopStatePolling：停止状态轮询 */
  stopStatePolling(): void {
    if (this._pollTimer) {
      clearInterval(this._pollTimer)
      this._pollTimer = null
    }
  }

  /* sendMessage：发送消息 + SSE 流式接收 */
  async sendMessage(text: string): Promise<void> {
    if (!text.trim() || this.sending.value) return

    // 追加用户消息
    this.messages.push({ role: 'user', content: text })
    this._scrollToBottom()

    // 占位 assistant 消息
    const streamMsg: ChatMessage = { role: 'assistant', content: '', isStreaming: true }
    this.messages.push(streamMsg)
    const idx = this.messages.length - 1
    this.sending.value = true
    this._abortCtl = new AbortController()

    try {
      const resp = await fetch(`${API_BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: this._abortCtl.signal,
      })

      if (resp.status === 503) {
        const data = await resp.json()
        this.messages.splice(idx, 1) // 删占位
        this._toast.show(data.message || '请先配置 Chat', 'error')
        return
      }
      if (resp.status === 409) {
        const data = await resp.json()
        this.messages.splice(idx, 1)
        this._toast.show(data.message || 'AI 正在思考', 'info')
        return
      }
      if (!resp.ok) {
        this.messages.splice(idx, 1)
        this._toast.show(`请求失败 ${resp.status}`, 'error')
        return
      }

      // SSE 读取
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          if (part.startsWith(':')) continue // 心跳
          if (!part.startsWith('data:')) continue
          try {
            const payload = JSON.parse(part.slice(5).trim())
            if (payload.type === 'token') {
              this.messages[idx].content += payload.content || ''
              this._scrollToBottom()
            } else if (payload.type === 'error') {
              this._toast.show(`AI 响应出错: ${payload.message}`, 'error')
            } else if (payload.type === 'done') {
              this.messages[idx].isStreaming = false
            }
          } catch {
            // JSON parse error → skip
          }
        }
      }
      // 兜底标记完成
      this.messages[idx].isStreaming = false
    } catch (e: any) {
      if (e.name === 'AbortError') {
        this.messages[idx].content += ' [已取消]'
        this.messages[idx].isStreaming = false
      } else {
        this._toast.show(String(e), 'error')
        this.messages.splice(idx, 1)
      }
    } finally {
      this.sending.value = false
      this._abortCtl = null
    }
  }

  /* abortStream：取消当前流式响应 */
  abortStream(): void {
    this._abortCtl?.abort()
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
