<script setup lang="ts">
import { memoryViewModel } from '../index'

const vm = memoryViewModel

function handleRefresh() { vm.entityTab.loadStats() }
</script>

<template>
  <div class="entity-panel">
    <div class="entity-toolbar">
      <span class="entity-title">实体统计</span>
      <button class="btn-refresh" @click="handleRefresh" :disabled="vm.entityTab.loading.value">
        {{ vm.entityTab.loading.value ? '加载中...' : '刷新' }}
      </button>
    </div>

    <div class="entity-content">
      <div v-if="vm.entityTab.loading.value" class="entity-loading">加载中...</div>
      <template v-else>
        <div class="stat-cards">
          <div class="stat-card">
            <div class="stat-value">{{ vm.entityTab.stats.value.entity_nodes }}</div>
            <div class="stat-label">实体数量</div>
            <div class="stat-sub">entity_nodes</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ vm.entityTab.stats.value.mentions }}</div>
            <div class="stat-label">提及记录</div>
            <div class="stat-sub">mentions</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ vm.entityTab.stats.value.memory_relations }}</div>
            <div class="stat-label">记忆关系</div>
            <div class="stat-sub">memory_relations</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ vm.entityTab.stats.value.entity_relations }}</div>
            <div class="stat-label">实体关系</div>
            <div class="stat-sub">entity_relations</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ vm.entityTab.stats.value.typed_entity_relations }}</div>
            <div class="stat-label">类型关系</div>
            <div class="stat-sub">typed_entity_relations</div>
          </div>
        </div>

        <div class="graph-status-card">
          <div class="status-header">内存图状态</div>
          <div class="status-body">
            <span class="status-dot" :class="{ loaded: vm.entityTab.stats.value.graph_loaded }"></span>
            <span class="status-text">{{ vm.entityTab.stats.value.graph_loaded ? '已加载' : '未加载' }}</span>
            <span class="status-divider">|</span>
            <span class="status-info">节点: {{ vm.entityTab.stats.value.graph_nodes }}</span>
            <span class="status-divider">|</span>
            <span class="status-info">边: {{ vm.entityTab.stats.value.graph_edges }}</span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.entity-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.entity-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(100, 120, 200, 0.15);
  flex-shrink: 0;
  background: rgba(2, 5, 16, 0.6);
  backdrop-filter: blur(8px);
}
.entity-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(140, 170, 220, 0.9);
  letter-spacing: 0.05em;
}
.btn-refresh {
  padding: 4px 14px;
  border: 1px solid rgba(100, 140, 220, 0.25);
  border-radius: 6px;
  background: rgba(30, 50, 100, 0.3);
  color: rgba(140, 170, 220, 0.8);
  cursor: pointer;
  font-size: 12px;
  letter-spacing: 0.05em;
  transition: all 0.2s;
}
.btn-refresh:hover {
  background: rgba(60, 90, 180, 0.35);
  color: #c8d8f0;
  border-color: rgba(100, 160, 255, 0.45);
  box-shadow: 0 0 10px rgba(80, 130, 255, 0.2);
}
.btn-refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.entity-content {
  flex: 1;
  padding: 20px 16px;
  overflow: auto;
}
.entity-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: rgba(100, 130, 180, 0.5);
  font-size: 13px;
  letter-spacing: 0.1em;
}
.stat-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: #1a1d27;
  border-radius: 10px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #a78bfa;
  line-height: 1;
}
.stat-label {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 4px;
}
.stat-sub {
  font-size: 10px;
  color: #475569;
  font-family: monospace;
}
.graph-status-card {
  background: #1a1d27;
  border-radius: 10px;
  padding: 16px 20px;
}
.status-header {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
}
.status-body {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #475569;
  flex-shrink: 0;
}
.status-dot.loaded {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
}
.status-text {
  font-size: 13px;
  color: #94a3b8;
}
.status-divider {
  color: #2d3149;
}
.status-info {
  font-size: 12px;
  color: #64748b;
}
</style>