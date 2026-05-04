<script setup lang="ts">
import { wikiViewModel } from '../WikiViewModel'
</script>

<template>
  <div class="side-panel active">
    <div class="wscard-col">
      <div class="wscard">
        <div class="wsc-label">文件数</div>
        <div class="wsc-value">{{ wikiViewModel.rawFiles.value.length || '-' }}</div>
      </div>
      <div class="wscard">
        <div class="wsc-label">总大小</div>
        <div class="wsc-value">{{ wikiViewModel.rawFiles.value.length ? wikiViewModel.formatSize(wikiViewModel.totalSize) : '-' }}</div>
        <div class="wsc-sub">{{ wikiViewModel.rawFiles.value.length }} 个 .md 文件</div>
      </div>
      <div class="wscard">
        <div class="wsc-label">索引状态</div>
        <div class="wsc-value" :style="{ fontSize: '15px', color: wikiViewModel.indexStatusText.color }">
          {{ wikiViewModel.indexStatusText.text }}
        </div>
      </div>
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
.wscard-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wscard {
  background: #12141c;
  border: 1px solid #2d3149;
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wsc-label {
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 600;
}
.wsc-value {
  font-size: 22px;
  font-weight: 700;
  color: #e2e8f0;
}
.wsc-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}
</style>
