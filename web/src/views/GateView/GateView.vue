<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi'

const { fetchJson, postJson } = useApi()

// ── 状态 ──────────────────────────────────────────────────────
const botId = ref('')
const secret = ref('')
const hasSecret = ref(false)
const status = ref('stopped')
const connected = ref(false)
const lastError = ref('')
const showSecret = ref(false)
const loading = ref(false)
const statusMsg = ref('')
const statusType = ref<'success' | 'error' | ''>('')
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

// ── 初始化 ────────────────────────────────────────────────────
onMounted(async () => {
  await loadConfig()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

function startPolling() {
  pollTimer.value = setInterval(pollStatus, 3000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function pollStatus() {
  try {
    const r = await fetchJson<{ status: string; connected: boolean; last_error: string }>('/gate/status')
    status.value = r.status
    connected.value = r.connected
    if (r.last_error) {
      lastError.value = r.last_error
    }
  } catch {
    // ignore polling errors
  }
}

function showMsg(msg: string, type: 'success' | 'error' = 'success') {
  statusMsg.value = msg
  statusType.value = type
  setTimeout(() => { statusMsg.value = '' }, 4000)
}

// ── API ───────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const r = await fetchJson<{ bot_id: string; has_secret: boolean; status: string; connected: boolean; last_error: string }>('/gate/config')
    botId.value = r.bot_id
    hasSecret.value = r.has_secret
    status.value = r.status
    connected.value = r.connected
    lastError.value = r.last_error
  } catch (e) {
    console.error('Failed to load gate config:', e)
  }
}

async function saveConfig() {
  if (!botId.value.trim() || !secret.value.trim()) {
    showMsg('BotID 和 Secret 不能为空', 'error')
    return
  }
  loading.value = true
  try {
    const r = await postJson('/gate/config', { bot_id: botId.value, secret: secret.value })
    if (r.ok) {
      hasSecret.value = true
      showMsg('配置已保存')
    } else {
      showMsg(r.message || '保存失败', 'error')
    }
  } catch (e: any) {
    showMsg('保存失败: ' + (e.message || '未知错误'), 'error')
  } finally {
    loading.value = false
  }
}

async function connect() {
  loading.value = true
  try {
    const r = await postJson('/gate/connect', {})
    if (r.ok) {
      showMsg(r.message || '连接中…')
    } else {
      showMsg(r.message || '连接失败', 'error')
    }
  } catch (e: any) {
    showMsg('连接失败: ' + (e.message || '未知错误'), 'error')
  } finally {
    loading.value = false
  }
}

async function disconnect() {
  loading.value = true
  try {
    const r = await postJson('/gate/disconnect', {})
    showMsg(r.message || '已断开')
  } catch (e: any) {
    showMsg('断开失败: ' + (e.message || '未知错误'), 'error')
  } finally {
    loading.value = false
  }
}

// ── 状态显示 ──────────────────────────────────────────────────
const statusLabel = {
  stopped: '未连接',
  connecting: '连接中…',
  connected: '已连接',
  error: '连接异常',
}

const statusColor = {
  stopped: '#64748b',
  connecting: '#fbbf24',
  connected: '#86efac',
  error: '#fca5a5',
}
</script>

<template>
  <div class="gate-page">
    <!-- 页头 -->
    <header class="page-header">
      <div class="title-wrap">
        <div class="page-title">Gate · 机器人接入</div>
        <div class="page-sub">配置企业微信智能机器人 WebSocket 长连接</div>
      </div>
    </header>

    <!-- 状态通知 -->
    <Transition name="fade">
      <div v-if="statusMsg" class="status-bar" :class="statusType">{{ statusMsg }}</div>
    </Transition>

    <!-- 连接状态卡片 -->
    <section class="card status-card">
      <div class="card-row">
        <span class="card-label">连接状态</span>
        <span class="status-dot" :style="{ background: statusColor[status as keyof typeof statusColor] || '#64748b' }"></span>
        <span class="status-text" :style="{ color: statusColor[status as keyof typeof statusColor] || '#64748b' }">
          {{ statusLabel[status as keyof typeof statusLabel] || status }}
        </span>
        <span v-if="lastError && status === 'error'" class="error-detail" :title="lastError">{{ lastError.slice(0, 60) }}</span>
      </div>
      <div class="card-row">
        <span class="card-label">当前机器人</span>
        <span class="card-value">{{ botId || '未配置' }}</span>
      </div>
      <div class="card-actions">
        <button
          class="btn btn-primary"
          :disabled="loading || connected || !botId || !hasSecret"
          @click="connect"
        >
          {{ loading && status === 'connecting' ? '连接中…' : '启动连接' }}
        </button>
        <button
          class="btn btn-danger"
          :disabled="loading || !connected"
          @click="disconnect"
        >
          断开连接
        </button>
      </div>
    </section>

    <!-- 机器人配置卡片 -->
    <section class="card config-card">
      <div class="card-title">机器人凭证配置</div>
      <p class="card-desc">
        在企业微信管理后台 → 应用管理 → 智能机器人 创建机器人后，
        将 BotID 和 Secret 填入下方。
      </p>

      <div class="form-group">
        <label class="form-label">BotID</label>
        <input
          v-model="botId"
          type="text"
          class="form-input"
          placeholder="请输入机器人 BotID"
          :disabled="connected"
        />
      </div>

      <div class="form-group">
        <label class="form-label">Secret</label>
        <div class="input-wrap">
          <input
            v-model="secret"
            :type="showSecret ? 'text' : 'password'"
            class="form-input"
            :placeholder="hasSecret ? '已保存 Secret，留空则使用已有值' : '请输入 Secret'"
            :disabled="connected"
          />
          <button class="btn-icon" @click="showSecret = !showSecret" :title="showSecret ? '隐藏' : '显示'">
            {{ showSecret ? '🙈' : '👁' }}
          </button>
        </div>
      </div>

      <div class="form-actions">
        <button
          class="btn btn-primary"
          :disabled="loading || connected"
          @click="saveConfig"
        >
          {{ loading ? '保存中…' : '保存配置' }}
        </button>
      </div>
    </section>

    <!-- 使用说明 -->
    <section class="card help-card">
      <div class="card-title">接入说明</div>
      <ol class="help-list">
        <li>登录 <a href="https://work.weixin.qq.com/wework_admin" target="_blank" rel="noopener">企业微信管理后台</a> → 应用管理 → 智能机器人</li>
        <li>创建机器人，接入方式选择 <strong>WebSocket 长连接</strong></li>
        <li>复制 BotID 和 Secret 填入上方配置框并保存</li>
        <li>点击「启动连接」建立长连接，状态变为「已连接」即成功</li>
        <li>用户在企业微信中向机器人发送消息，AiBrain 将自动回复</li>
      </ol>
    </section>

    <!-- 消息处理说明 -->
    <section class="card help-card">
      <div class="card-title">注意事项</div>
      <ul class="help-list">
        <li>每个机器人同一时间只能保持一个长连接</li>
        <li>连接由系统自动维护心跳（30秒间隔）和断线重连</li>
        <li>当前仅支持 <strong>文本消息</strong> 的处理和回复</li>
        <li>断开连接后需重新手动启动</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.gate-page {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  box-sizing: border-box;
  flex: 1;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #e2e8f0;
}

.page-sub {
  font-size: 11px;
  color: #64748b;
}

.status-bar {
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
}

.status-bar.success {
  background: #22c55e18;
  border: 1px solid #22c55e44;
  color: #86efac;
}

.status-bar.error {
  background: #ef444418;
  border: 1px solid #ef444444;
  color: #fca5a5;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.card {
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #e2e8f0;
}

.card-desc {
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}

.card-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-label {
  font-size: 11px;
  color: #64748b;
  min-width: 72px;
}

.card-value {
  font-size: 12px;
  color: #94a3b8;
  font-family: ui-monospace, monospace;
}

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

/* 状态圆点 */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-text {
  font-size: 12px;
  font-weight: 600;
}

.error-detail {
  font-size: 10px;
  color: #fca5a5;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 表单 */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-label {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
}

.input-wrap {
  display: flex;
  gap: 6px;
  align-items: center;
}

.form-input {
  flex: 1;
  background: #14161f;
  border: 1px solid #2d3149;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  color: #e2e8f0;
  outline: none;
  transition: border-color 0.2s;
  font-family: ui-monospace, monospace;
}

.form-input:focus {
  border-color: #7c3aed88;
}

.form-input:disabled {
  opacity: 0.5;
}

.form-input::placeholder {
  color: #475569;
}

.btn-icon {
  background: transparent;
  border: 1px solid #2d3149;
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.btn-icon:hover {
  background: #1e293b;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

/* 按钮 */
.btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  user-select: none;
}

.btn-primary {
  background: #7c3aed;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #6d28d9;
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: default;
}

.btn-danger {
  background: transparent;
  color: #fca5a5;
  border: 1px solid #ef444444;
}

.btn-danger:hover:not(:disabled) {
  background: #ef444418;
}

.btn-danger:disabled {
  opacity: 0.4;
  cursor: default;
}

/* 帮助列表 */
.help-card {
  gap: 8px;
}

.help-list {
  margin: 0;
  padding: 0 0 0 18px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.help-list li {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.5;
}

.help-list a {
  color: #a78bfa;
  text-decoration: none;
}

.help-list a:hover {
  text-decoration: underline;
}

.help-list strong {
  color: #e2e8f0;
}
</style>
