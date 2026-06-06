<script setup lang="ts">
import { settingsViewModel } from '../index'

const chatTab = settingsViewModel.chatTab

function getTab(): any {
  return chatTab
}
</script>

<template>
  <div class="tab-content" v-if="chatTab">
    <div class="config-form">
      <!-- Chat Provider -->
      <div class="form-row">
        <label>Provider</label>
        <select
          :value="chatTab.form['chat_provider']"
          @change="(e) => {
            const v = (e.target as HTMLSelectElement).value
            chatTab.form['chat_provider'] = v
            chatTab.onProviderChange(v)
          }"
        >
          <option v-for="p in chatTab.providerOptions" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>

      <!-- Model -->
      <div class="form-row">
        <label>Model</label>
        <input
          type="text"
          :value="chatTab.form['chat_model']"
          @input="chatTab.form['chat_model'] = ($event.target as HTMLInputElement).value"
          placeholder="如 gpt-4o-mini"
        />
      </div>

      <!-- API Key -->
      <div class="form-row">
        <label>API Key</label>
        <input
          type="password"
          :value="chatTab.form['chat_api_key']"
          @input="chatTab.form['chat_api_key'] = ($event.target as HTMLInputElement).value"
          placeholder="从对应平台获取"
          autocomplete="off"
        />
      </div>

      <!-- Base URL -->
      <div class="form-row">
        <label>Base URL</label>
        <input
          type="text"
          :value="chatTab.form['chat_base_url']"
          @input="chatTab.form['chat_base_url'] = ($event.target as HTMLInputElement).value"
          placeholder="可选，留空用接口默认端点"
        />
      </div>

      <!-- Idle Enabled -->
      <div class="form-row checkbox-row">
        <label>空闲思考</label>
        <label class="switch">
          <input
            type="checkbox"
            :checked="!!chatTab.form['idle_enabled']"
            @change="chatTab.form['idle_enabled'] = ($event.target as HTMLInputElement).checked"
          />
          <span class="slider"></span>
        </label>
        <span class="hint">开启后 AI 会定时自由联想</span>
      </div>

      <!-- Idle Interval -->
      <div class="form-row" v-if="chatTab.form['idle_enabled']">
        <label>思考间隔 (秒)</label>
        <input
          type="number"
          :value="chatTab.form['idle_interval_seconds']"
          @input="chatTab.form['idle_interval_seconds'] = parseInt(($event.target as HTMLInputElement).value) || 45"
          min="15"
          max="600"
          step="5"
        />
        <span class="hint">15–600 秒</span>
      </div>

      <!-- System Persona -->
      <div class="form-row vertical">
        <label>System Persona</label>
        <textarea
          :value="chatTab.form['system_persona']"
          @input="chatTab.form['system_persona'] = ($event.target as HTMLTextAreaElement).value"
          placeholder="定义 AI 的人格和行为方式..."
          rows="4"
          class="persona-textarea"
        ></textarea>
        <div class="hint-row">
          <span class="hint">支持占位符：{now} 时间 | {memory} 检索记忆 | {persona} 人格</span>
          <span class="char-count">{{ String(chatTab.form['system_persona'] ?? '').length }} / 8000</span>
        </div>
      </div>

      <!-- Max Context Messages -->
      <div class="form-row">
        <label>上下文消息数</label>
        <input
          type="number"
          :value="chatTab.form['max_context_messages']"
          @input="chatTab.form['max_context_messages'] = parseInt(($event.target as HTMLInputElement).value) || 20"
          min="5"
          max="100"
        />
      </div>

      <!-- Trim Keep Last -->
      <div class="form-row">
        <label>消息保留上限</label>
        <input
          type="number"
          :value="chatTab.form['trim_keep_last']"
          @input="chatTab.form['trim_keep_last'] = parseInt(($event.target as HTMLInputElement).value) || 1000"
          min="100"
          max="10000"
          step="100"
        />
      </div>

      <!-- Recall Own Thoughts -->
      <div class="form-row checkbox-row">
        <label>回忆自身思绪</label>
        <label class="switch">
          <input
            type="checkbox"
            :checked="!!chatTab.form['recall_own_thoughts']"
            @change="chatTab.form['recall_own_thoughts'] = ($event.target as HTMLInputElement).checked"
          />
          <span class="slider"></span>
        </label>
        <span class="hint">v2 占位，暂不生效</span>
      </div>
    </div>

    <!-- Test 状态条 -->
    <div v-if="chatTab.testStatus.value" class="test-status" :class="chatTab.testStatus.value">
      <span class="status-icon">
        {{ chatTab.testStatus.value === 'testing' ? '⏳' : chatTab.testStatus.value === 'ok' ? '✅' : '❌' }}
      </span>
      <span class="status-text">{{ chatTab.testMessage.value }}</span>
      <span v-if="chatTab.testStatus.value === 'ok' && chatTab.testLatency.value" class="status-latency">
        {{ chatTab.testLatency.value }}ms
      </span>
    </div>

    <div class="header-actions">
      <button class="btn btn-secondary" @click="chatTab.testConnection()" :disabled="chatTab.testStatus.value === 'testing'">
        {{ chatTab.testStatus.value === 'testing' ? '测试中...' : '🔌 Test Connection' }}
      </button>
      <button class="btn btn-secondary" @click="chatTab.reset()">恢复默认</button>
      <button class="btn btn-primary" @click="chatTab.save()">保存</button>
    </div>
  </div>
</template>

<style scoped>
.tab-content { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.config-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; align-items: center; gap: 12px; }
.form-row.vertical { flex-direction: column; align-items: stretch; }
.form-row.vertical label { min-width: unset; }
.form-row label { font-size: 12px; color: #94a3b8; min-width: 120px; }
.form-row input, .form-row select, .form-row textarea {
  flex: 1; background: #0f1117; border: 1px solid #2d3149; border-radius: 6px;
  color: #e2e8f0; padding: 6px 10px; font-size: 13px; font-family: inherit; outline: none;
}
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: #7c3aed; }
.form-row select { cursor: pointer; }
.form-row textarea { resize: vertical; min-height: 80px; }

/* ── 开关样式 ── */
.checkbox-row { gap: 8px; }
.switch { position: relative; display: inline-block; width: 36px; height: 20px; flex-shrink: 0; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background: #2d3149; border-radius: 20px; transition: .2s;
}
.slider::before {
  content: ''; position: absolute; height: 14px; width: 14px;
  left: 3px; bottom: 3px; background: #94a3b8; border-radius: 50%; transition: .2s;
}
.switch input:checked + .slider { background: #7c3aed; }
.switch input:checked + .slider::before { transform: translateX(16px); background: #fff; }

.hint { font-size: 11px; color: #64748b; }
.hint-row { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
.char-count { font-size: 11px; color: #475569; font-family: monospace; }

/* ── Test 状态 ── */
.test-status {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #0f1117; border: 1px solid #2d3149; border-radius: 6px;
  font-size: 12px; color: #94a3b8;
}
.test-status.testing { border-color: #fbbf24; color: #fbbf24; }
.test-status.ok { border-color: #86efac; color: #86efac; }
.test-status.err { border-color: #fca5a5; color: #fca5a5; }
.status-icon { font-size: 14px; }
.status-text { flex: 1; }
.status-latency { color: #64748b; font-family: monospace; }

.header-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity .2s; }
.btn:active { transform: scale(.98); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover:not(:disabled) { opacity: .85; }
.btn-secondary { background: #1e293b; color: #94a3b8; border: 1px solid #2d3149; }
.btn-secondary:hover:not(:disabled) { border-color: #475569; }
</style>
