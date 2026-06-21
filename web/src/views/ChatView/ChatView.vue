<script setup lang="ts">
import { ref, onMounted, onActivated, onDeactivated, onUnmounted, nextTick, computed } from 'vue'
import { chatViewModel } from './index'
import { useRouter } from 'vue-router'

const router = useRouter()
const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const showSettings = ref(false)
const systemPersona = ref('')
const saving = ref(false)
const savedTip = ref(false)
const quotePreview = ref('')
const quoteIndex = ref(-1)
const showScrollBtn = ref(false)
const ticker = ref(0)
let tickerTimer: ReturnType<typeof setInterval> | null = null

function onScroll() {
  const el = messagesEl.value
  if (!el) return
  showScrollBtn.value = el.scrollHeight - el.scrollTop - el.clientHeight > 100
}

onMounted(async () => {
  chatViewModel.setScrollFn(scrollToBottom)
  await chatViewModel.loadMessages()
  chatViewModel.startStatePolling()
  // 启动计时器，实时更新 streaming 消息的耗时
  tickerTimer = setInterval(() => {
    ticker.value++
    const msgs = chatViewModel.messages
    for (let i = 0; i < msgs.length; i++) {
      if (msgs[i].isStreaming && msgs[i].duration !== undefined) {
        msgs[i].duration = parseFloat((msgs[i].duration! + 0.1).toFixed(1))
      }
    }
  }, 100)
})

// KeepAlive 切回时刷新状态和滚动到底部
onActivated(() => {
  chatViewModel.loadState()
  scrollToBottom()
})

// KeepAlive 离开时停止轮询节省资源
onDeactivated(() => {
  chatViewModel.stopStatePolling()
})

onUnmounted(() => {
  chatViewModel.stopStatePolling()
  if (tickerTimer) clearInterval(tickerTimer)
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

const proactiveLoading = ref(false)

async function handleProactive() {
  if (proactiveLoading.value) return
  proactiveLoading.value = true
  await chatViewModel.triggerProactive()
  proactiveLoading.value = false
}

async function handleSend() {
  let text = inputText.value.trim()
  if (!text || chatViewModel.sending.value) return
  if (quotePreview.value) {
    text = `> ${quotePreview.value}\n\n${text}`
    quotePreview.value = ''
  }
  inputText.value = ''
  await chatViewModel.sendMessage(text)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function handleStop() {
  chatViewModel.abortStream()
}

function handleClear() {
  chatViewModel.clearChat()
}

async function openSettings() {
  showSettings.value = true
  savedTip.value = false
  try {
    const resp = await fetch('/settings/chat')
    const json = await resp.json()
    systemPersona.value = json.data?.system_persona || ''
  } catch {
    systemPersona.value = ''
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await fetch('/settings/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system_persona: systemPersona.value }),
    })
    savedTip.value = true
    setTimeout(() => { savedTip.value = false }, 2000)
  } catch (e) {
    console.error('save settings failed:', e)
  } finally {
    saving.value = false
  }
}

function closeSettings() {
  showSettings.value = false
}

function quoteMsg(text: string, index: number) {
  const lines = text.split('\n').filter(Boolean)
  let quote = lines.slice(0, 3).join('\n')
  if (lines.length > 3) quote += '\n...'
  quotePreview.value = quote
  quoteIndex.value = index
  nextTick(() => {
    const ta = document.querySelector('.chat-input') as HTMLTextAreaElement
    ta?.focus()
  })
}

function jumpToQuote() {
  if (quoteIndex.value < 0) return
  const el = messagesEl.value
  if (!el) return
  const msgs = el.querySelectorAll('.message')
  const target = msgs[quoteIndex.value] as HTMLElement
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.style.transition = 'background 0.5s'
    target.style.background = 'rgba(124, 58, 237, 0.15)'
    setTimeout(() => { target.style.background = '' }, 1500)
  }
  clearQuote()
}

function clearQuote() {
  quotePreview.value = ''
  quoteIndex.value = -1
}

async function copyMsgContent(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  // 浮动提示
  const flash = document.createElement('div')
  flash.className = 'copy-flash'
  flash.textContent = '已复制'
  document.body.appendChild(flash)
  setTimeout(() => flash.remove(), 1200)
}

/* 简单 markdown 渲染 */
function renderContent(msg: { role: string; content: string }) {
  if (msg.role === 'user') return escapeHtml(msg.content)
  // assistant: 简单 markdown（粗体、代码、换行）
  let html = escapeHtml(msg.content)
  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="lang-$1">$2</code></pre>')
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 粗体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // 斜体
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 换行
  html = html.replace(/\n/g, '<br>')
  return html
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/* 意识状态条 */
const stateLabel = computed(() => {
  const s = chatViewModel.loopState
  if (s.is_busy) return { icon: '🟡', text: '思考中...', cls: 'busy' }
  if (s.idle_enabled) {
    const count = s.idle_count
    return { icon: '🟢', text: `已思考 ${count} 次`, cls: 'idle' }
  }
  return { icon: '⚪', text: '意识流已暂停', cls: 'paused' }
})

/* Token 用量 */
const tokenPercent = computed(() => {
  const max = chatViewModel.loopState.max_context_tokens || 400000
  const used = chatViewModel.loopState.prompt_tokens || 0
  return Math.min((used / max) * 100, 100)
})

const tokenColor = computed(() => {
  const p = tokenPercent.value / 100
  // HSL 插值：0% → 绿(120°)  50% → 黄(60°)  100% → 红(0°)
  const hue = Math.round(120 - p * 120)
  return `hsl(${hue}, 80%, 45%)`
})

/* 时间格式化 */
function timeAgo(ts: number | null): string {
  if (!ts) return ''
  const diff = Math.floor((Date.now() / 1000) - ts)
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  return `${Math.floor(diff / 3600)}小时前`
}

/* 渲染时间分隔线：日期变化时显示 */
function getDateSeparator(currentTime: string, prevTime: string | null): string {
  if (!currentTime) return ''
  const curDate = currentTime.slice(0, 10) // "2026-06-08"
  if (!prevTime) return curDate // 第一条
  const prevDate = prevTime.slice(0, 10)
  if (curDate !== prevDate) return curDate
  return ''
}

/* 工具标签 */
const TOOL_ICONS: Record<string, string> = {
  memory_search: '🔍', memory_store: '💾',
  file_search: '📁', read_file: '📖',
  list_directory: '📂', web_fetch: '🌐',
  plan: '📋',
}

const TOOL_LABELS: Record<string, string> = {
  memory_search: '搜索记忆', memory_store: '保存记忆',
  file_search: '搜索文件', read_file: '读取文件',
  list_directory: '浏览目录', web_fetch: '获取网页',
  plan: '计划管理',
}

function toolIcon(name: string): string {
  return TOOL_ICONS[name] || '🔧'
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name
}

function toolArgsText(args: Record<string, any>): string {
  const parts: string[] = []
  if (args.pattern) parts.push(`"${args.pattern}"`)
  if (args.query) parts.push(`"${args.query}"`)
  if (args.path) parts.push(args.path)
  if (args.file_pattern) parts.push(args.file_pattern)
  if (args.url) parts.push(args.url)
  return parts.join('  ') || ''
}

/* 格式化消息时间：显示 HH:mm:ss */
function formatMsgTime(time: string): string {
  if (!time) return ''
  const m = time.match(/\d{2}:\d{2}:\d{2}/)
  return m ? m[0] : ''
}
</script>

<template>
  <div class="chat-wrap">
    <!-- 顶部状态条 -->
    <div class="status-bar" :class="stateLabel.cls">
      <span class="status-icon">{{ stateLabel.icon }}</span>
      <span class="status-text">{{ stateLabel.text }}</span>
      <template v-if="chatViewModel.loopState.idle_enabled && chatViewModel.loopState.last_thought_at">
        <span class="status-detail">上次 {{ timeAgo(chatViewModel.loopState.last_thought_at) }}</span>
      </template>
      <button class="status-btn" @click="openSettings" title="系统提示词">⚙</button>
      <button class="status-btn" @click="handleClear" title="清空对话">🗑</button>
    </div>

    <!-- 消息列表 -->
    <div class="messages" ref="messagesEl" @scroll="onScroll">
      <div v-if="!chatViewModel.messages.length" class="empty-hint">
        <div class="empty-icon">💭</div>
        <div>开始与 AiBrain 对话</div>
        <div class="empty-sub">AI 会自动检索记忆库来理解上下文</div>
      </div>

      <template v-for="(msg, i) in chatViewModel.messages" :key="i">
        <!-- 日期分隔线 -->
        <div v-if="getDateSeparator(msg.created_at || '', (chatViewModel.messages[i-1]?.created_at || null))" class="date-separator">
          {{ getDateSeparator(msg.created_at || '', (chatViewModel.messages[i-1]?.created_at || null)) }}
        </div>
        <div
          class="message"
          :class="[
            msg.role,
            { thought: msg.is_thought === 1 },
          ]"
        >
          <!-- 思绪标记 -->
          <span v-if="msg.is_thought === 1" class="thought-badge">💭 思绪</span>
          <!-- 记忆搜索步骤展示 -->
          <div v-if="msg.memorySteps?.length" class="memory-steps">
            <div v-for="(ms, mi) in msg.memorySteps" :key="mi" class="memory-step">
              <span class="memory-step-icon">{{ ms.status === 'done' ? '✅' : '⏳' }}</span>
              <span class="memory-step-name">{{ ms.step === 'vector_search' ? '语义搜索' : ms.step === 'graph_recall' ? '图扩散召回' : ms.step }}</span>
            </div>
          </div>
          <!-- 工具调用展示 -->
          <div v-if="msg.toolCalls?.length" class="tool-calls">
            <div v-for="(tc, ti) in msg.toolCalls" :key="ti" class="tool-call">
              <span class="tool-call-icon">{{ toolIcon(tc.name) }}</span>
              <span class="tool-call-name">{{ toolLabel(tc.name) }}</span>
              <span class="tool-call-args">{{ toolArgsText(tc.arguments || {}) }}</span>
            </div>
          </div>
          <!-- 消息内容 -->
          <div class="msg-content" v-html="renderContent(msg)"></div>
          <!-- 流式状态 + 光标（仅流式期间显示） -->
          <div v-if="msg.isStreaming" class="stream-status">
            <span class="stream-label">{{ chatViewModel.currentStatus.value }}</span>
            <span class="cursor">▌</span>
          </div>
          <!-- 时间戳 + 耗时 -->
          <div v-if="msg.created_at" class="msg-footer" :class="msg.role">
            <span class="msg-time">{{ formatMsgTime(msg.created_at) }}</span>
            <span v-if="msg.role==='assistant' && msg.duration!==undefined" class="msg-duration">{{ msg.duration.toFixed(1) }}s</span>
          </div>
        </div>
        <!-- 气泡操作栏 -->
        <div class="msg-actions" :class="msg.role" v-if="!msg.isStreaming">
          <button class="action-btn" @click="copyMsgContent(msg.content)" title="复制">📋</button>
          <button class="action-btn" @click="quoteMsg(msg.content, i)" title="引用">💬</button>
        </div>
      </template>
      <!-- 滚动到底部按钮 -->
      <button v-if="showScrollBtn" class="scroll-bottom-btn" @click="scrollToBottom">⬇</button>
    </div>

    <!-- 引用预览 -->
    <div v-if="quotePreview" class="quote-preview">
      <div class="quote-preview-bar"></div>
      <div class="quote-preview-text">{{ quotePreview }}</div>
      <button class="quote-preview-close" @click="clearQuote">✕</button>
    </div>
    <!-- 输入区 -->
    <div class="input-area">
      <textarea
        v-model="inputText"
        class="chat-input"
        placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
        rows="1"
        @keydown="handleKeydown"
        :disabled="chatViewModel.sending.value"
      ></textarea>
      <button
        v-if="chatViewModel.sending.value"
        class="send-btn stop-btn"
        @click="handleStop"
        title="停止"
      >⏹</button>
      <button
        v-else
        class="send-btn"
        @click="handleSend"
        :disabled="!inputText.trim()"
        title="发送"
      >➤</button>
      <button
        class="proactive-btn"
        @click="handleProactive"
        :disabled="proactiveLoading"
        title="猫猫主动说一句"
      >💬</button>
    </div>

    <!-- Token 用量 -->
    <div class="token-bar">
      <div class="token-bar-track">
        <div class="token-bar-fill" :style="{ width: tokenPercent + '%', background: tokenColor }"></div>
      </div>
      <span class="token-label">{{ (chatViewModel.loopState.prompt_tokens / 1000).toFixed(1) || 0 }}k / {{ (chatViewModel.loopState.max_context_tokens / 1000).toFixed(1) || '400' }}k ({{ tokenPercent.toFixed(1) }}%)</span>
    </div>

    <!-- 系统提示词设置弹窗 -->
    <Teleport to="body">
      <div v-if="showSettings" class="modal-overlay" @click.self="closeSettings">
        <div class="modal-panel">
          <div class="modal-header">
            <div class="modal-title">系统提示词</div>
            <button class="modal-close" @click="closeSettings">✕</button>
          </div>
          <div class="modal-body">
            <textarea
              v-model="systemPersona"
              class="modal-textarea"
              placeholder="输入系统提示词..."
              rows="8"
            ></textarea>
          </div>
          <div class="modal-footer">
            <span v-if="savedTip.value" class="save-tip">✓ 已保存</span>
            <button class="btn-cancel" @click="closeSettings">取消</button>
            <button class="btn-save" @click="saveSettings" :disabled="saving.value">
              {{ saving.value ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  flex: 1;
}

/* ── 状态条 ── */
.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: #1a1d27;
  border-bottom: 1px solid #2d3149;
  font-size: 12px;
  color: #94a3b8;
  flex-shrink: 0;
}
.status-bar.busy { color: #fbbf24; }
.status-bar.idle { color: #86efac; }
.status-bar.paused { color: #64748b; }
.status-icon { font-size: 10px; }
.status-text { font-weight: 600; }
.status-detail { margin-left: auto; font-size: 11px; color: #64748b; }
.status-btn {
  background: none; border: none; color: #64748b; font-size: 14px;
  cursor: pointer; padding: 2px 4px; border-radius: 4px; transition: all .15s;
}
.status-btn:hover { color: #a78bfa; background: #2d3149; }

/* ── 消息列表 ── */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: relative;
}

.empty-hint {
  text-align: center;
  color: #475569;
  padding: 60px 20px;
  font-size: 14px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-sub { font-size: 12px; color: #334155; margin-top: 6px; }

/* ── 消息气泡 ── */
.message {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  position: relative;
  user-select: text;
}

.message.user {
  align-self: flex-end;
  background: #7c3aed;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant {
  align-self: flex-start;
  background: #1e293b;
  color: #e2e8f0;
  border-bottom-left-radius: 4px;
}

.message.thought {
  background: rgba(139, 92, 246, 0.12);
  border-left: 3px solid #7c3aed;
  font-style: italic;
  color: #c4b5fd;
  max-width: 70%;
}

/* ── 工具调用（气泡内） ── */
.tool-calls {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 6px;
}
.tool-call {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(124, 58, 237, 0.1);
  border: 1px solid rgba(124, 58, 237, 0.2);
  border-radius: 5px;
  padding: 3px 10px;
  font-size: 11px;
}
.tool-call-icon {
  font-size: 12px;
}
.tool-call-name {
  color: #a78bfa;
  font-weight: 600;
  white-space: nowrap;
}

/* ── 记忆搜索步骤（气泡内） ── */
.memory-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
.memory-step {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.25);
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 11px;
}
.memory-step-icon {
  font-size: 10px;
}
.memory-step-name {
  color: #34d399;
  font-weight: 600;
  white-space: nowrap;
}
.tool-call-args {
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thought-badge {
  display: inline-block;
  font-size: 10px;
  font-style: normal;
  color: #a78bfa;
  margin-bottom: 4px;
  opacity: 0.7;
}

.msg-duration {
  font-size: 10px;
  color: #64748b;
  opacity: 0.6;
}

/* 时间戳底部栏 */
.msg-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.msg-footer.assistant {
  justify-content: flex-start;
}
.msg-footer.user {
  justify-content: flex-end;
}
.msg-time {
  font-size: 11px;
  color: #e2e8f0;
}

/* 日期分隔线 */
.date-separator {
  text-align: center;
  font-size: 11px;
  color: #475569;
  padding: 8px 0;
  position: relative;
}
.date-separator::before,
.date-separator::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 30%;
  height: 1px;
  background: #2d3149;
}
.date-separator::before { left: 0; }
.date-separator::after { right: 0; }

.msg-content {
  user-select: text;
  -webkit-user-select: text;
}
.msg-content :deep(pre) {
  background: #0f1117;
  border: 1px solid #2d3149;
  border-radius: 6px;
  padding: 8px 10px;
  overflow-x: auto;
  margin: 6px 0;
  font-size: 12px;
}
.msg-content :deep(code) {
  background: #0f1117;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
}
.msg-content :deep(pre code) {
  background: none;
  padding: 0;
}

/* 流式状态 + 光标（仅流式期间显示） */
.stream-status {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
}
.stream-label {
  font-size: 10px;
  color: #a78bfa;
  opacity: 0.7;
}
.cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
  color: #a78bfa;
  font-weight: bold;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ── 引用预览 ── */
.quote-preview {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 16px;
  background: #1a1d27;
  border-top: 1px solid #2d3149;
  border-bottom: 1px solid #2d3149;
  flex-shrink: 0;
}
.quote-preview-bar {
  width: 3px;
  flex-shrink: 0;
  align-self: stretch;
  background: #7c3aed;
  border-radius: 2px;
}
.quote-preview-text {
  flex: 1;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  white-space: pre-wrap;
  word-break: break-all;
}
.quote-preview-close {
  background: none;
  border: none;
  color: #64748b;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  flex-shrink: 0;
}
.quote-preview-close:hover {
  color: #e2e8f0;
  background: #2d3149;
}

/* ── Token 用量 ── */
.token-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 16px;
  background: #0f1117;
  border-top: 1px solid #1a1d27;
  flex-shrink: 0;
}
.token-bar-track {
  flex: 1;
  height: 4px;
  background: #1e293b;
  border-radius: 2px;
  overflow: hidden;
}
.token-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease, background 0.5s ease;
}
.token-label {
  font-size: 10px;
  color: #e2e8f0;
  white-space: nowrap;
  min-width: 80px;
  text-align: right;
}

/* ── 输入区 ── */
.input-area {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 16px;
  background: #1a1d27;
  border-top: 1px solid #2d3149;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  background: #0f1117;
  border: 1px solid #2d3149;
  border-radius: 8px;
  color: #e2e8f0;
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
  resize: none;
  outline: none;
  min-height: 40px;
  max-height: 120px;
  line-height: 1.5;
}
.chat-input:focus { border-color: #7c3aed; }
.chat-input:disabled { opacity: 0.5; }
.chat-input::placeholder { color: #475569; }

.send-btn {
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 8px;
  background: #7c3aed;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
  flex-shrink: 0;
}
.send-btn:hover:not(:disabled) { background: #6d28d9; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-btn:active:not(:disabled) { transform: scale(0.95); }

.stop-btn {
  background: #dc2626;
}
.stop-btn:hover { background: #b91c1c; }

.proactive-btn {
  width: 36px;
  height: 36px;
  border: 1px solid #475569;
  border-radius: 8px;
  background: transparent;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
  flex-shrink: 0;
}
.proactive-btn:hover:not(:disabled) {
  background: #334155;
  color: #e2e8f0;
  border-color: #7c3aed;
}
.proactive-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 滚动到底部按钮 ── */
.scroll-bottom-btn {
  position: absolute;
  bottom: 60px;
  right: 24px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #1e293b;
  border: 1px solid #2d3149;
  color: #94a3b8;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  z-index: 10;
  transition: all .15s;
}
.scroll-bottom-btn:hover {
  background: #263044;
  color: #cbd5e1;
}

/* ── 气泡操作栏 ── */
.msg-actions {
  display: flex;
  gap: 4px;
  margin-top: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}
.msg-actions.assistant {
  align-self: flex-start;
  margin-left: 4px;
}
.msg-actions.user {
  align-self: flex-end;
  margin-right: 4px;
  flex-direction: row-reverse;
}
.message:hover + .msg-actions,
.msg-actions:hover {
  opacity: 1;
}
.action-btn {
  background: none;
  border: 1px solid transparent;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
  transition: all 0.15s;
}
.action-btn:hover {
  color: #94a3b8;
  border-color: #2d3149;
  background: #1e293b;
}

/* ── 复制浮动提示 ── */
:global(.copy-flash) {
  position: fixed;
  top: 36px;
  left: 50%;
  transform: translateX(-50%);
  background: #22c55e22;
  color: #86efac;
  border: 1px solid #22c55e44;
  font-size: 11px;
  padding: 4px 16px;
  border-radius: 6px;
  pointer-events: none;
  z-index: 9999;
  animation: copyFade 1.2s ease forwards;
}
@keyframes copyFade {
  0% { opacity: 1; transform: translateX(-50%) translateY(0); }
  100% { opacity: 0; transform: translateX(-50%) translateY(-12px); }
}

/* ── 设置弹窗 ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  width: 500px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #2d3149;
}
.modal-title {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}
.modal-close {
  background: none;
  border: none;
  color: #64748b;
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}
.modal-close:hover { color: #e2e8f0; background: #2d3149; }
.modal-body {
  padding: 16px 20px;
}
.modal-textarea {
  width: 100%;
  background: #0f1117;
  border: 1px solid #2d3149;
  border-radius: 8px;
  color: #e2e8f0;
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  line-height: 1.5;
  min-height: 120px;
}
.modal-textarea:focus { border-color: #7c3aed; }
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #2d3149;
}
.save-tip {
  font-size: 12px;
  color: #86efac;
  margin-right: auto;
}
.btn-cancel {
  background: #1e293b;
  border: 1px solid #2d3149;
  color: #94a3b8;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.btn-cancel:hover { color: #e2e8f0; }
.btn-save {
  background: #7c3aed;
  border: none;
  color: #fff;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.btn-save:hover { background: #6d28d9; }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
