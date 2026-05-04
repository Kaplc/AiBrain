<script setup lang="ts">
import { useSideSettings } from './SideSettings'
const vm = useSideSettings()
</script>

<template>
  <div class="side-panel active">
    <div class="settings-section">
      <div class="form-group">
        <label class="form-label">Wiki 目录</label>
        <input v-model="vm.formWikiDir.value" class="form-input" type="text" placeholder="如: wiki">
      </div>
      <div class="form-group">
        <label class="form-label">LightRAG 数据目录</label>
        <input v-model="vm.formLightragDir.value" class="form-input" type="text" placeholder="如: rag/lightrag_data">
      </div>
      <div class="form-group">
        <label class="form-label">语言</label>
        <select v-model="vm.formLanguage.value" class="form-select">
          <option value="Chinese">Chinese</option>
          <option value="English">English</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">分块大小 (token)</label>
        <input v-model.number="vm.formChunkSize.value" class="form-input" type="number" placeholder="1200" min="200" max="8000">
      </div>
      <div class="form-group">
        <label class="form-label">搜索超时 (秒)</label>
        <input v-model.number="vm.formTimeout.value" class="form-input" type="number" placeholder="30" min="5" max="300">
      </div>
      <button class="btn-save" :disabled="vm.saving.value" @click="vm.saveSettings()">
        {{ vm.saving.value ? '保存中...' : '保存设置' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.side-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 14px;
}
.side-panel.active {
  display: flex;
}
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
}
.form-input,
.form-select {
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid #2d3149;
  background: #12141c;
  color: #e2e8f0;
  font-size: 13px;
  outline: none;
  transition: border-color .2s;
}
.form-input:focus,
.form-select:focus {
  border-color: #7c3aed;
}
.btn-save {
  padding: 8px 24px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s;
  border: none;
  user-select: none;
  background: #7c3aed33;
  color: #a78bfa;
  border: 1px solid #7c3aed44;
}
.btn-save:hover {
  background: #7c3aed55;
}
.btn-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
