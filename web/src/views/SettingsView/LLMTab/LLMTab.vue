<script setup lang="ts">
import { computed } from 'vue'
import { settingsViewModel } from '../index'

const llmTab = settingsViewModel.llmTab

// 是否显示接口类型分组（后端有 optionGroups 时才显示 radio 按钮组）
const hasGroups = computed(() => (llmTab.form.optionGroups?.length ?? 0) > 0)
const interfaceTypeField = computed(() =>
  llmTab.form.fields.find(f => f.key === 'provider')
)
</script>

<template>
  <div class="tab-content">
    <div class="config-form">
      <div v-if="!llmTab.form.fields.length" class="loading">加载中...</div>

      <!-- 接口类型：radio 按钮组（替代 dropdown，更直观） -->
      <div v-if="hasGroups && interfaceTypeField" class="form-row interface-row">
        <label>接口类型</label>
        <div class="radio-group">
          <label
            v-for="g in llmTab.form.optionGroups"
            :key="g.protocol"
            class="radio-card"
            :class="{
              active: llmTab.form.values['provider'] === g.providers[0],
              [g.protocol]: true,
            }"
          >
            <input
              type="radio"
              :name="'interface_type'"
              :value="g.providers[0]"
              :checked="llmTab.form.values['provider'] === g.providers[0]"
              @change="(e) => {
                const v = (e.target as HTMLInputElement).value
                llmTab.form.values['provider'] = v
                llmTab.onProviderChange(v)
              }"
            />
            <div class="radio-content">
              <div class="radio-title">{{ g.providers[0] }}</div>
              <div class="radio-subtitle">{{ g.label }}</div>
              <div class="radio-path">{{ g.protocol === 'openai' ? '/v1/chat/completions' : '/v1/messages' }}</div>
            </div>
          </label>
        </div>
      </div>

      <!-- 其它字段：循环渲染，跳过 provider（已用 radio 处理） -->
      <template v-for="f in llmTab.form.fields" :key="f.key">
        <div v-if="f.key !== 'provider'" class="form-row">
          <label>{{ f.label }}</label>

          <!-- 普通 select（Mem0Tab 等其它地方可能用） -->
          <select
            v-if="f.type === 'select'"
            :value="llmTab.form.values[f.key]"
            @change="llmTab.form.values[f.key] = ($event.target as HTMLSelectElement).value"
          >
            <option v-for="opt in (f as any).options" :key="opt" :value="opt">{{ opt }}</option>
          </select>

          <!-- password -->
          <input
            v-else-if="f.type === 'password'"
            type="password"
            :value="llmTab.form.values[f.key]"
            @input="llmTab.form.values[f.key] = ($event.target as HTMLInputElement).value"
            :placeholder="String((f as any).placeholder ?? f.default ?? '')"
            autocomplete="off"
          />

          <!-- number -->
          <input
            v-else-if="f.type === 'number'"
            type="number"
            :value="llmTab.form.values[f.key]"
            @input="llmTab.form.values[f.key] = ($event.target as HTMLInputElement).value"
            :placeholder="String(f.default ?? '')"
            step="0.1"
            min="0"
          />

          <!-- text（默认） -->
          <input
            v-else
            type="text"
            :value="llmTab.form.values[f.key]"
            @input="llmTab.form.values[f.key] = ($event.target as HTMLInputElement).value"
            :placeholder="String((f as any).placeholder ?? f.default ?? '')"
          />
        </div>
      </template>
    </div>

    <!-- Test 状态条 -->
    <div v-if="llmTab.testStatus.value" class="test-status" :class="llmTab.testStatus.value">
      <span class="status-icon">
        {{ llmTab.testStatus.value === 'testing' ? '⏳' : llmTab.testStatus.value === 'ok' ? '✅' : '❌' }}
      </span>
      <span class="status-text">{{ llmTab.testMessage.value }}</span>
      <span v-if="llmTab.testStatus.value === 'ok' && llmTab.testLatency.value" class="status-latency">
        {{ llmTab.testLatency.value }}ms
      </span>
    </div>

    <div class="header-actions">
      <button class="btn btn-secondary" @click="llmTab.testConnection()" :disabled="llmTab.testStatus.value === 'testing'">
        {{ llmTab.testStatus.value === 'testing' ? '测试中...' : '🔌 Test Connection' }}
      </button>
      <button class="btn btn-secondary" @click="llmTab.reset()">恢复默认</button>
      <button class="btn btn-primary" @click="llmTab.save()">保存</button>
    </div>
  </div>
</template>

<style scoped>
.tab-content { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.config-form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; align-items: center; gap: 12px; }
.form-row label { font-size: 12px; color: #94a3b8; min-width: 120px; }
.form-row input, .form-row select {
  flex: 1; background: #0f1117; border: 1px solid #2d3149; border-radius: 6px;
  color: #e2e8f0; padding: 6px 10px; font-size: 13px; font-family: inherit; outline: none;
}
.form-row input:focus, .form-row select:focus { border-color: #7c3aed; }
.form-row select { cursor: pointer; }
.loading { font-size: 12px; color: #64748b; text-align: center; padding: 20px; }

/* ── 接口类型 radio 按钮组 ── */
.interface-row { align-items: flex-start; }
.radio-group { display: flex; gap: 10px; flex: 1; }
.radio-card {
  flex: 1; display: flex; align-items: flex-start; gap: 10px;
  background: #0f1117; border: 1px solid #2d3149; border-radius: 8px;
  padding: 12px 14px; cursor: pointer; transition: all .15s;
  position: relative;
}
.radio-card:hover { border-color: #475569; background: #13161f; }
.radio-card.active { border-color: #7c3aed; background: #1a1230; box-shadow: 0 0 0 1px #7c3aed inset; }
.radio-card.openai.active { border-color: #10b981; background: #0a1f17; box-shadow: 0 0 0 1px #10b981 inset; }
.radio-card.anthropic.active { border-color: #d97706; background: #1f160a; box-shadow: 0 0 0 1px #d97706 inset; }
.radio-card input[type="radio"] { position: absolute; opacity: 0; pointer-events: none; }
.radio-card::before {
  content: ''; display: inline-block; width: 14px; height: 14px; min-width: 14px;
  border: 2px solid #475569; border-radius: 50%; margin-top: 2px;
  transition: all .15s;
}
.radio-card.active::before { border-color: currentColor; background: currentColor; box-shadow: 0 0 0 3px #1a1d27 inset; }
.radio-card.openai { color: #6ee7b7; }
.radio-card.anthropic { color: #fcd34d; }
.radio-content { flex: 1; }
.radio-title { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.radio-card.openai .radio-title { color: #6ee7b7; }
.radio-card.anthropic .radio-title { color: #fcd34d; }
.radio-subtitle { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.radio-path { font-size: 10px; color: #64748b; font-family: monospace; margin-top: 4px; }

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
