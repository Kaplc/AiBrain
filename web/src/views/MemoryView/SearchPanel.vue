<script setup lang="ts">
import { memoryViewModel } from './index'

const vm = memoryViewModel
</script>

<template>
  <div class="tab-panel">
    <div class="search-bar">
      <input
        v-model="vm.searchTab.input.value"
        type="text"
        placeholder="搜索相关记忆..."
        :disabled="vm.searchTab.loading.value"
        @input="vm.searchTab.debounceSearch()"
        @keydown.enter="vm.searchTab.search()"
      />
      <button class="btn btn-primary" :disabled="vm.searchTab.loading.value" @click="vm.searchTab.search()">搜索</button>
      <div class="search-history-wrap">
        <button class="btn btn-icon-sm" @click.stop="vm.searchTab.showHistory.value = !vm.searchTab.showHistory.value" title="搜索历史">🕐</button>
        <div v-show="vm.searchTab.showHistory.value" class="sh-dropdown">
          <div class="sh-dropdown-header">
            <span>搜索历史</span>
            <button class="sh-clear" @click="vm.searchTab.clearHistory()">清空</button>
          </div>
          <div class="sh-dropdown-list">
            <div v-if="!vm.searchTab.history.value.length" class="sh-empty">暂无搜索历史</div>
            <div v-for="h in vm.searchTab.history.value" :key="h" class="history-item" @click="vm.searchTab.searchFromHistory(h)">{{ h }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="memory-list-container">
      <div v-if="vm.searchTab.loading.value" class="search-loading">
        <span class="spinner"></span>
        <span>搜索中...</span>
      </div>
      <div class="memory-list">
        <template v-if="vm.searchTab.activeQuery.value">
          <template v-if="vm.searchTab.results.value.length">
            <div v-for="m in vm.searchTab.results.value" :key="m.id" class="memory-card search-result">
              <div class="memory-content">
                <div class="memory-text">{{ m.text }}</div>
                <div class="memory-meta">
                  <span class="memory-time">{{ vm.searchTab.formatTime(m.timestamp) }}</span>
                  <span v-if="m.score !== undefined" class="memory-score">相似度 {{ (m.score * 100).toFixed(1) }}%</span>
                  <span class="memory-id">{{ (m.id || '').slice(0, 8) }}...</span>
                </div>
              </div>
              <button class="del-btn" @click="vm.storeTab.delete(m.id)" title="删除">✕</button>
            </div>
          </template>
          <div v-else-if="!vm.searchTab.loading.value" class="empty">
            <div class="empty-icon">🔍</div>
            <div class="empty-text">没有找到相关记忆</div>
          </div>
        </template>
        <div v-else-if="!vm.searchTab.loading.value" class="empty">
          <div class="empty-icon">🔍</div>
          <div class="empty-text">搜索记忆以查看结果</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.search-bar input { flex: 1; background: #1e2235; color: #e2e8f0; border: 1px solid #2d3149; border-radius: 6px; padding: 8px 12px; font-size: 13px; }
.search-bar input:focus { outline: none; border-color: #7c3aed; }
.search-bar input::placeholder { color: #64748b; }
.btn { padding: 6px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover { background: #6d28d9; }
.btn-icon-sm { background: none; border: 1px solid #2d3149; color: #94a3b8; cursor: pointer; font-size: 12px; padding: 4px 8px; border-radius: 4px; }
.search-history-wrap { position: relative; }
.sh-dropdown { position: absolute; top: 100%; right: 0; margin-top: 4px; background: #1e2235; border: 1px solid #2d3149; border-radius: 6px; min-width: 200px; z-index: 100; }
.sh-dropdown-header { display: flex; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid #2d3149; font-size: 12px; color: #94a3b8; }
.sh-clear { background: none; border: none; color: #ef4444; cursor: pointer; font-size: 12px; }
.sh-dropdown-list { max-height: 200px; overflow: auto; }
.sh-empty { padding: 12px; text-align: center; color: #64748b; font-size: 12px; }
.history-item { padding: 8px 12px; cursor: pointer; font-size: 13px; color: #e2e8f0; }
.history-item:hover { background: #2d3149; }
.memory-list-container { flex: 1; overflow: auto; }
.search-loading { display: flex; align-items: center; gap: 8px; padding: 20px; color: #94a3b8; font-size: 14px; }
.spinner { width: 16px; height: 16px; border: 2px solid #2d3149; border-top-color: #7c3aed; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.memory-list { display: flex; flex-direction: column; gap: 8px; }
.memory-card { background: #1e2235; border-radius: 8px; padding: 12px; display: flex; gap: 12px; }
.memory-card.search-result { border: 1px solid #2d3149; }
.memory-content { flex: 1; min-width: 0; }
.memory-text { font-size: 13px; color: #e2e8f0; line-height: 1.5; word-break: break-word; }
.memory-meta { display: flex; gap: 12px; margin-top: 6px; font-size: 11px; color: #64748b; }
.memory-score { color: #a78bfa; }
.del-btn { background: none; border: none; color: #64748b; cursor: pointer; font-size: 14px; padding: 4px; }
.del-btn:hover { color: #ef4444; }
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; color: #64748b; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
