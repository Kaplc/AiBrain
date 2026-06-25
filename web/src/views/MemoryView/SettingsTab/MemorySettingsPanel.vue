<script setup lang="ts">
import { memoryViewModel } from '../index'

const settingsTab = memoryViewModel.settingsTab
</script>

<template>
  <div class="settings-panel">
    <div v-if="settingsTab.loading.value" class="panel-loading">加载中...</div>

    <template v-else>
      <div class="settings-section">
        <div class="section-title">记忆存储模式</div>
        <div class="notice">
          ✨ LLM 编码已固定开启 — 保存时自动提取情景节点，搜索时启用图增强
        </div>
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

/* ── 提示信息 ── */
.notice {
  font-size: 13px;
  color: #a78bfa;
  padding: 12px 16px;
  background: #1e1b4b;
  border: 1px solid #4c1d95;
  border-radius: 8px;
  line-height: 1.6;
}
</style>
