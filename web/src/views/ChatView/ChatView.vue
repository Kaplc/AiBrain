<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { chatViewModel } from './index'
import { useRouter } from 'vue-router'

const router = useRouter()
const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)

onMounted(async () => {
  chatViewModel.setScrollFn(scrollToBottom)
  await chatViewModel.loadMessages()
  chatViewModel.startStatePolling()
})

onUnmounted(() => {
  chatViewModel.stopStatePolling()
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatViewModel.sending.value) return
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

function goToSettings() {
  router.push('/settings?tab=chat')
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

/* 时间格式化 */
function timeAgo(ts: number | null): string {
  if (!ts) return ''
  const diff = Math.floor((Date.now() / 1000) - ts)
  if (diff < 60) return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  return `${Math.floor(diff / 3600)}小时前`
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
      <button class="status-btn" @click="goToSettings" title="Chat 设置">⚙</button>
      <button class="status-btn" @click="handleClear" title="清空对话">🗑</button>
    </div>

    <!-- 消息列表 -->
    <div class="messages" ref="messagesEl">
      <div v-if="!chatViewModel.messages.length" class="empty-hint">
        <div class="empty-icon">💭</div>
        <div>开始与 AiBrain 对话</div>
        <div class="empty-sub">AI 会自动检索记忆库来理解上下文</div>
      </div>

      <div
        v-for="(msg, i) in chatViewModel.messages"
        :key="i"
        class="message"
        :class="[
          msg.role,
          { thought: msg.is_thought === 1 },
        ]"
      >
        <!-- 思绪标记 -->
        <span v-if="msg.is_thought === 1" class="thought-badge">💭 思绪</span>
        <!-- 消息内容 -->
        <div class="msg-content" v-html="renderContent(msg)"></div>
        <!-- 流式光标 -->
        <span v-if="msg.isStreaming" class="cursor">▌</span>
      </div>
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
    </div>
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

.thought-badge {
  display: inline-block;
  font-size: 10px;
  font-style: normal;
  color: #a78bfa;
  margin-bottom: 4px;
  opacity: 0.7;
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

/* 流式光标 */
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
</style>
