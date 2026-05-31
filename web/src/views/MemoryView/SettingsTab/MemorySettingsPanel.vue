<script setup lang="ts">
import { memoryViewModel } from '../index'

const settingsTab = memoryViewModel.settingsTab
</script>

<template>
  <div class="settings-panel">
    <div v-if="settingsTab.loading.value" class="panel-loading">加载中...</div>

    <template v-else>
      <!-- ── LLM 模式开关 ── -->
      <div class="settings-section">
        <div class="section-title">记忆存储模式</div>

        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-label">LLM 模式</span>
            <span class="setting-desc">
              开启后，保存时调用大模型拆分事实+提取实体，搜索时启用图增强，合并时支持AI精炼。<br>
              关闭后，全部操作仅依赖向量相似度，不消耗大模型额度。
            </span>
          </div>
          <label class="toggle-switch">
            <input type="checkbox" v-model="settingsTab.form.infer" />
            <span class="toggle-track">
              <span class="toggle-thumb"></span>
            </span>
          </label>
        </div>

        <div class="infer-hint" :class="settingsTab.form.infer ? 'hint-on' : 'hint-off'">
          <template v-if="settingsTab.form.infer">
            ✨ 当前：<b>智能模式</b> — 大模型提取实体 + 图增强搜索 + AI精炼合并
          </template>
          <template v-else>
            ⚡ 当前：<b>纯向量模式</b> — 搜索/保存/精炼均不调用大模型
          </template>
        </div>
      </div>

      <!-- ── 操作按钮 ── -->
      <div class="settings-actions">
        <button
          class="btn btn-primary"
          :disabled="settingsTab.saving.value"
          @click="settingsTab.save()"
        >
          {{ settingsTab.saving.value ? '保存中...' : '保存设置' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.settings-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 4px 0;
  overflow-y: auto;
}

.panel-loading {
  text-align: center;
  color: #64748b;
  font-size: 14px;
  padding: 40px;
}

/* ── 区块 ── */
.settings-section {
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 10px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #a78bfa;
  letter-spacing: 0.5px;
}

/* ── 单条设置行 ── */
.setting-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.setting-label {
  font-size: 14px;
  color: #e2e8f0;
  font-weight: 600;
}

.setting-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.6;
}

/* ── Toggle 开关 ── */
.toggle-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;
  margin-top: 2px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.toggle-track {
  width: 44px;
  height: 24px;
  background: #374151;
  border-radius: 12px;
  position: relative;
  transition: background 0.2s;
  display: block;
}

.toggle-switch input:checked + .toggle-track {
  background: #7c3aed;
}

.toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
  display: block;
}

.toggle-switch input:checked + .toggle-track .toggle-thumb {
  transform: translateX(20px);
}

/* ── 状态提示 ── */
.infer-hint {
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  line-height: 1.5;
}

.hint-on {
  background: #1e1b4b;
  color: #a78bfa;
  border: 1px solid #4c1d95;
}

.hint-off {
  background: #1c2a1c;
  color: #6ee7b7;
  border: 1px solid #065f46;
}

/* ── 操作按钮 ── */
.settings-actions {
  display: flex;
  gap: 8px;
}

.btn {
  padding: 8px 20px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #7c3aed;
  color: #fff;
}

.btn-primary:not(:disabled):hover {
  opacity: 0.85;
}
</style>
