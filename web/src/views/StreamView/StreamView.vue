<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { streamViewModel } from './StreamViewModel'
import StoreStreamItem from './StoreStreamItem.vue'
import SearchStreamItem from './SearchStreamItem.vue'
import DeleteStreamItem from './DeleteStreamItem.vue'

onMounted(() => streamViewModel.onMounted())
onUnmounted(() => streamViewModel.onUnmounted())

const expandedIds = ref(new Set<number>())

function toggleExpand(id: number) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
  expandedIds.value = new Set(expandedIds.value)
}

function isExpanded(id: number): boolean {
  return expandedIds.value.has(id)
}

function getItemComponent(action: string) {
  if (action === 'store') return StoreStreamItem
  if (action === 'search') return SearchStreamItem
  if (action === 'delete') return DeleteStreamItem
  return StoreStreamItem
}

function scoreColor(score: number): string {
  if (score >= 0.8) return '#22c55e'
  if (score >= 0.6) return '#eab308'
  return '#64748b'
}

function sourceLabel(source: string): string {
  if (source === 'semantic') return '语义'
  if (source === 'scene_diffusion') return '情景'
  if (source === 'graph') return '图谱'
  return source
}
</script>

<template>
  <div class="stream-wrap">
    <div class="stream-header">
      <div class="stream-title">记忆流</div>
      <div class="stream-count">{{ streamViewModel.totalCount.value }}</div>
    </div>

    <div class="stream-columns">
      <!-- ── 存储列 ── -->
      <div class="stream-column">
        <div class="stream-column-header">
          <div class="stream-column-dot store"></div>
          <span>保存</span>
          <span class="stream-column-count">{{ streamViewModel.storeStream.countText.value }}</span>
        </div>

        <!-- 保存输入 -->
        <div class="stream-action-form">
          <textarea
            v-model="streamViewModel.storeInput.value"
            class="stream-action-textarea"
            placeholder="输入要保存的记忆文本..."
            rows="2"
            @keydown.ctrl.enter="streamViewModel.storeMemory()"
          ></textarea>
          <button
            class="stream-action-btn store-btn"
            :disabled="streamViewModel.storeLoading.value || !streamViewModel.storeInput.value.trim()"
            @click="streamViewModel.storeMemory()"
          >
            <span v-if="streamViewModel.storeLoading.value" class="action-spinner"></span>
            <span v-else>保存</span>
          </button>
        </div>

        <!-- 存储流列表 -->
        <div class="stream-list">
          <div v-if="streamViewModel.storeStream.items.value.length === 0" class="stream-empty">
            暂无写入记录
          </div>
          <StoreStreamItem
            v-for="item in streamViewModel.storeStream.items.value"
            :key="item.id"
            :item="item"
            :is-expanded="isExpanded(item.id)"
            :is-new="streamViewModel.isNew(item.id)"
            @toggle="toggleExpand"
          />
        </div>
      </div>

      <!-- ── 搜索列 ── -->
      <div class="stream-column">
        <div class="stream-column-header">
          <div class="stream-column-dot search"></div>
          <span>查询</span>
          <span class="stream-column-count">{{ streamViewModel.searchStream.countText.value }}</span>
        </div>

        <!-- 搜索输入 -->
        <div class="stream-action-form">
          <input
            v-model="streamViewModel.searchInput.value"
            class="stream-action-input"
            placeholder="搜索长时记忆..."
            @keydown.enter="streamViewModel.searchMemory()"
          />
          <button
            class="stream-action-btn search-btn"
            :disabled="streamViewModel.searchLoading.value || !streamViewModel.searchInput.value.trim()"
            @click="streamViewModel.searchMemory()"
          >
            <span v-if="streamViewModel.searchLoading.value" class="action-spinner"></span>
            <span v-else>搜索</span>
          </button>
        </div>

        <!-- 搜索结果 -->
        <div v-if="streamViewModel.searchShowResults.value" class="search-results-wrap">
          <div class="search-results-header">
            <span class="search-results-title">搜索结果 ({{ streamViewModel.searchResults.value.length }})</span>
            <button class="search-results-close" @click="streamViewModel.closeSearchResults()">✕</button>
          </div>
          <div v-if="streamViewModel.searchResults.value.length === 0" class="search-empty">
            无结果
          </div>
          <div
            v-for="(r, idx) in streamViewModel.searchResults.value"
            :key="r.memory_id || idx"
            class="search-result-item"
          >
            <div class="search-result-top">
              <span class="search-result-source" :class="r.source">{{ sourceLabel(r.source) }}</span>
              <span class="search-result-score" :style="{ color: scoreColor(r.score) }">
                {{ (r.score * 100).toFixed(0) }}
              </span>
            </div>
            <div class="search-result-text">{{ r.text }}</div>
            <div class="search-result-bottom">
              <span class="search-result-id">{{ r.memory_id?.slice(0, 16) }}…</span>
            </div>
          </div>
        </div>

        <!-- 搜索流列表 -->
        <div class="stream-list">
          <div v-if="streamViewModel.searchStream.items.value.length === 0" class="stream-empty">
            暂无查询记录
          </div>
          <SearchStreamItem
            v-for="item in streamViewModel.searchStream.items.value"
            :key="item.id"
            :item="item"
            :is-expanded="isExpanded(item.id)"
            :is-new="streamViewModel.isNew(item.id)"
            @toggle="toggleExpand"
          />
        </div>
      </div>

      <!-- ── 删除列 ── -->
      <div class="stream-column">
        <div class="stream-column-header">
          <div class="stream-column-dot delete"></div>
          <span>删除</span>
          <span class="stream-column-count">{{ streamViewModel.deleteStream.countText.value }}</span>
        </div>

        <!-- 删除输入 -->
        <div class="stream-action-form">
          <input
            v-model="streamViewModel.deleteInput.value"
            class="stream-action-input"
            placeholder="输入 memory_id 删除..."
            @keydown.enter="streamViewModel.deleteMemory()"
          />
          <button
            class="stream-action-btn delete-btn"
            :disabled="streamViewModel.deleteLoading.value || !streamViewModel.deleteInput.value.trim()"
            @click="streamViewModel.deleteMemory()"
          >
            <span v-if="streamViewModel.deleteLoading.value" class="action-spinner"></span>
            <span v-else>删除</span>
          </button>
        </div>

        <!-- 删除流列表 -->
        <div class="stream-list">
          <div v-if="streamViewModel.deleteStream.items.value.length === 0" class="stream-empty">
            暂无删除记录
          </div>
          <DeleteStreamItem
            v-for="item in streamViewModel.deleteStream.items.value"
            :key="item.id"
            :item="item"
            :is-expanded="isExpanded(item.id)"
            :is-new="streamViewModel.isNew(item.id)"
            @toggle="toggleExpand"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stream-wrap {
  padding: 24px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  gap: 16px;
  box-sizing: border-box;
  height: 100%;
}

.stream-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.stream-title {
  font-size: 16px;
  font-weight: 700;
  color: #e2e8f0;
}

.stream-count {
  font-size: 12px;
  color: #64748b;
}

.stream-columns {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.stream-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  height: 100%;
}

.stream-column-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  padding-bottom: 8px;
  border-bottom: 1px solid #2d3149;
  flex-shrink: 0;
}

.stream-column-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.stream-column-dot.store  { background: #22c55e; box-shadow: 0 0 6px #22c55e66; }
.stream-column-dot.search { background: #3b82f6; box-shadow: 0 0 6px #3b82f666; }
.stream-column-dot.delete { background: #ef4444; box-shadow: 0 0 6px #ef444466; }

.stream-column-count {
  margin-left: auto;
  font-size: 11px;
  color: #64748b;
  font-weight: 400;
}

/* ── 操作表单 ── */

.stream-action-form {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.stream-action-textarea {
  flex: 1;
  min-width: 0;
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  color: #e2e8f0;
  resize: none;
  font-family: inherit;
  line-height: 1.5;
}

.stream-action-textarea:focus {
  outline: none;
  border-color: #6366f1;
}

.stream-action-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 6px;
  padding: 0 10px;
  font-size: 12px;
  color: #e2e8f0;
}

.stream-action-input:focus {
  outline: none;
  border-color: #6366f1;
}

.stream-action-btn {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  transition: opacity 0.15s;
}

.stream-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.store-btn {
  background: #22c55e;
  color: #0f172a;
}

.search-btn {
  background: #3b82f6;
  color: #fff;
}

.delete-btn {
  background: #ef4444;
  color: #fff;
}

.action-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 搜索结果 ── */

.search-results-wrap {
  background: #1a1d27;
  border: 1px solid #3b82f6;
  border-radius: 8px;
  padding: 8px 10px;
  max-height: 300px;
  overflow-y: auto;
  flex-shrink: 0;
}

.search-results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid #2d3149;
}

.search-results-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
}

.search-results-close {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
}

.search-results-close:hover {
  color: #e2e8f0;
}

.search-empty {
  text-align: center;
  color: #475569;
  padding: 20px 0;
  font-size: 12px;
}

.search-result-item {
  padding: 6px 4px;
  border-bottom: 1px solid #2d3149;
}

.search-result-item:last-child {
  border-bottom: none;
}

.search-result-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}

.search-result-source {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #2d3149;
  color: #64748b;
}

.search-result-source.semantic {
  color: #22c55e;
  background: #22c55e1a;
}

.search-result-source.scene_diffusion {
  color: #a78bfa;
  background: #a78bfa1a;
}

.search-result-source.graph {
  color: #f59e0b;
  background: #f59e0b1a;
}

.search-result-score {
  font-size: 11px;
  font-weight: 600;
  margin-left: auto;
}

.search-result-text {
  font-size: 12px;
  color: #cbd5e1;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.search-result-bottom {
  margin-top: 3px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-result-id {
  font-size: 10px;
  color: #475569;
  font-family: monospace;
}

/* ── 流列表 ── */

.stream-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.stream-empty {
  text-align: center;
  color: #475569;
  padding: 40px 0;
  font-size: 13px;
}
</style>