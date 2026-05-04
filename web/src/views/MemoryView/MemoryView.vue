<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { memoryViewModel } from './index'

onMounted(() => memoryViewModel.onMounted())
onUnmounted(() => memoryViewModel.onUnmounted())
</script>

<template>
  <div class="memory-layout">
    <!-- Top nav -->
    <nav class="memory-nav">
      <div class="nav-tabs">
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'search' }" @click="memoryViewModel.switchTab('search')">搜索记忆</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'store' }" @click="memoryViewModel.switchTab('store')">保存记忆</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'organize' }" @click="memoryViewModel.switchTab('organize')">整理记忆</button>
      </div>
      <div class="nav-stat">
        <span class="stat-value">{{ memoryViewModel.animatingCount.value }}</span>
        <span class="stat-label">条记忆</span>
        <button class="btn-icon" @click="memoryViewModel.loadAll()" title="刷新">↻</button>
      </div>
    </nav>

    <!-- Search panel -->
    <div v-show="memoryViewModel.currentTab.value === 'search'" class="tab-panel">
      <div class="search-bar">
        <input
          v-model="memoryViewModel.searchTab.input.value"
          type="text"
          placeholder="搜索相关记忆..."
          :disabled="memoryViewModel.searchTab.loading.value"
          @input="memoryViewModel.searchTab.debounceSearch()"
          @keydown.enter="memoryViewModel.searchTab.search()"
        />
        <button class="btn btn-primary" :disabled="memoryViewModel.searchTab.loading.value" @click="memoryViewModel.searchTab.search()">搜索</button>
        <div class="search-history-wrap">
          <button class="btn btn-icon-sm" @click.stop="memoryViewModel.searchTab.showHistory.value = !memoryViewModel.searchTab.showHistory.value" title="搜索历史">🕐</button>
          <div v-show="memoryViewModel.searchTab.showHistory.value" class="sh-dropdown">
            <div class="sh-dropdown-header">
              <span>搜索历史</span>
              <button class="sh-clear" @click="memoryViewModel.searchTab.clearHistory()">清空</button>
            </div>
            <div class="sh-dropdown-list">
              <div v-if="!memoryViewModel.searchTab.history.value.length" class="sh-empty">暂无搜索历史</div>
              <div
                v-for="h in memoryViewModel.searchTab.history.value"
                :key="h"
                class="history-item"
                @click="memoryViewModel.searchTab.searchFromHistory(h)"
              >{{ h }}</div>
            </div>
          </div>
        </div>
      </div>
      <div class="memory-list-container">
        <div v-if="memoryViewModel.searchTab.loading.value" class="search-loading">
          <span class="spinner"></span>
          <span>搜索中...</span>
        </div>
        <div class="memory-list">
          <template v-if="memoryViewModel.searchTab.activeQuery.value">
            <template v-if="memoryViewModel.searchTab.results.value.length">
              <div v-for="m in memoryViewModel.searchTab.results.value" :key="m.id" class="memory-card search-result">
                <div class="memory-content">
                  <div class="memory-text">{{ m.text }}</div>
                  <div class="memory-meta">
                    <span class="memory-time">{{ memoryViewModel.searchTab.formatTime(m.timestamp) }}</span>
                    <span v-if="m.score !== undefined" class="memory-score">相似度 {{ (m.score * 100).toFixed(1) }}%</span>
                    <span class="memory-id">{{ (m.id || '').slice(0, 8) }}...</span>
                  </div>
                </div>
                <button class="del-btn" @click="memoryViewModel.storeTab.delete(m.id)" title="删除">✕</button>
              </div>
            </template>
            <div v-else class="empty">
              <div class="empty-icon">🔍</div>
              <div class="empty-text">没有找到相关记忆</div>
            </div>
          </template>
          <div v-else class="empty">
            <div class="empty-icon">🔍</div>
            <div class="empty-text">搜索记忆以查看结果</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Store panel -->
    <div v-show="memoryViewModel.currentTab.value === 'store'" class="tab-panel">
      <div class="store-area">
        <textarea
          v-model="memoryViewModel.storeTab.input.value"
          placeholder="输入要记住的内容..."
          @keydown.ctrl.enter="memoryViewModel.storeTab.save()"
        ></textarea>
        <button class="btn btn-primary" @click="memoryViewModel.storeTab.save()">保存记忆</button>
      </div>
      <div class="memory-list-container">
        <div class="memory-list">
          <template v-if="memoryViewModel.storeTab.memories.value.length">
            <div v-for="m in memoryViewModel.storeTab.memories.value" :key="m.id" class="memory-card">
              <div class="memory-content">
                <div class="memory-text">{{ m.text }}</div>
                <div class="memory-meta">
                  <span class="memory-time">{{ memoryViewModel.storeTab.formatTime(m.timestamp) }}</span>
                  <span class="memory-id">{{ (m.id || '').slice(0, 8) }}...</span>
                </div>
              </div>
              <button class="del-btn" @click="memoryViewModel.storeTab.delete(m.id)" title="删除">✕</button>
            </div>
          </template>
          <div v-else class="empty">
            <div class="empty-icon">🧠</div>
            <div class="empty-text">还没有任何记忆</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Organize panel -->
    <div v-show="memoryViewModel.currentTab.value === 'organize'" class="tab-panel">
      <div class="organize-toolbar">
        <select v-model="memoryViewModel.organizeTab.threshold.value" class="organize-select">
          <option value="0.90">严格去重</option>
          <option value="0.85">中等去重</option>
          <option value="0.80">宽松去重</option>
        </select>
        <button class="btn btn-accent" :disabled="memoryViewModel.organizeTab.busy.value" @click="memoryViewModel.organizeTab.start()">
          {{ memoryViewModel.organizeTab.busy.value ? '分析中...' : '开始分析' }}
        </button>
      </div>
      <div class="memory-list-container">
        <template v-if="memoryViewModel.organizeTab.busy.value">
          <div class="organize-loading">正在分析记忆相似度...</div>
        </template>
        <template v-else-if="memoryViewModel.organizeTab.groups.value.length">
          <div class="organize-header">
            <span>共发现 {{ memoryViewModel.organizeTab.groups.value.length }} 组相似</span>
          </div>
          <div class="organize-groups">
            <div
              v-for="(g, gi) in memoryViewModel.organizeTab.groups.value"
              :key="gi"
              class="organize-group-card"
              :class="{ 'og-applied': memoryViewModel.organizeTab.isApplied(gi) }"
            >
              <div class="og-label">
                组 {{ gi + 1 }} · 相似度 {{ g.similarity }} · {{ g.memories.length }} 条
                <button v-if="memoryViewModel.organizeTab.isApplied(gi)" class="btn-secondary-sm og-refine-btn" disabled>已写入</button>
                <button v-else-if="memoryViewModel.organizeTab.isRefined(gi)" class="btn-secondary-sm og-refine-btn" disabled>已精炼</button>
                <button v-else class="btn-secondary-sm og-refine-btn" @click="memoryViewModel.organizeTab.refineGroup(gi)">精炼此组</button>
              </div>
              <div v-for="(m, mi) in g.memories" :key="mi" class="og-item">
                <span class="og-idx">{{ mi + 1 }}</span>
                {{ m.text }}
              </div>

              <!-- Refined result -->
              <template v-for="(item, ri) in memoryViewModel.organizeTab.refined.value" :key="ri">
                <div v-if="item.group_id === gi" class="og-refine-result">
                  <div class="og-refine-divider"></div>
                  <div class="og-refine-label" :class="{ refined: item.refined }">
                    精炼结果{{ item.refined ? '' : '（降级）' }}
                  </div>
                  <div class="organize-refined-text" contenteditable="true" :id="'refinedText' + item.group_id">{{ item.refined_text }}</div>
                  <div class="organize-category">分类: {{ item.category || 'unknown' }}</div>
                  <div class="og-refine-actions">
                    <div class="organize-check">
                      <input type="checkbox" :id="'refinedCheck' + item.group_id" checked />
                      <label :for="'refinedCheck' + item.group_id">确认合并</label>
                    </div>
                    <button class="btn btn-sm btn-primary" @click="memoryViewModel.organizeTab.applySingle(item.group_id)">确认修改</button>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <!-- Footer -->
          <div v-if="memoryViewModel.organizeTab.refined.value.length" class="organize-refined">
            <div class="organize-footer-bar">
              <span class="organize-footer-stat">已精炼 {{ memoryViewModel.organizeTab.refined.value.length }}/{{ memoryViewModel.organizeTab.groups.value.length }} 组</span>
              <div class="organize-actions">
                <button v-if="memoryViewModel.organizeTab.unrefinedCount > 0" class="btn-secondary-sm" @click="memoryViewModel.organizeTab.refineAll()">
                  精炼剩余 {{ memoryViewModel.organizeTab.unrefinedCount }} 组
                </button>
                <button class="btn btn-sm btn-primary" @click="memoryViewModel.organizeTab.applyAll()">确认写入</button>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="empty">
          <div class="empty-icon">🧹</div>
          <div class="empty-text">点击"开始分析"扫描重复记忆</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-layout { display: flex; flex-direction: column; padding: 20px 24px; overflow: hidden; flex: 1; min-height: 0; box-sizing: border-box; height: 100%; gap: 16px; }

.memory-nav { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.nav-tabs { display: flex; gap: 4px; background: #1a1d27; border-radius: 10px; padding: 4px; }
.nav-tab { padding: 8px 20px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; color: #94a3b8; background: transparent; transition: all .2s; }
.nav-tab:hover { color: #e2e8f0; }
.nav-tab.active { background: #7c3aed; color: #fff; }
.nav-stat { display: flex; align-items: center; gap: 8px; }
.nav-stat .stat-value { font-size: 18px; font-weight: 700; color: #a78bfa; }
.nav-stat .stat-label { font-size: 12px; color: #64748b; }
.btn-icon { background: none; border: 1px solid #2d3149; color: #94a3b8; cursor: pointer; font-size: 14px; padding: 4px 10px; border-radius: 6px; transition: all .2s; }
.btn-icon:hover { color: #e2e8f0; border-color: #475569; }

.tab-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; overflow: hidden; }

.search-bar { display: flex; gap: 8px; flex-shrink: 0; }
.search-bar input { flex: 1; background: #1a1d27; border: 1px solid #2d3149; border-radius: 8px; color: #e2e8f0; padding: 10px 14px; font-size: 14px; outline: none; transition: border-color .2s; }
.search-bar input:focus { border-color: #7c3aed; }
.search-history-wrap { position: relative; flex-shrink: 0; }
.sh-dropdown { position: absolute; right: 0; top: 100%; margin-top: 6px; width: 280px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.4); z-index: 100; overflow: hidden; }
.sh-dropdown-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid #2d3149; }
.sh-dropdown-header span { font-size: 12px; font-weight: 600; color: #94a3b8; }
.sh-clear { background: none; border: none; color: #64748b; font-size: 11px; cursor: pointer; }
.sh-clear:hover { color: #ef4444; }
.sh-dropdown-list { max-height: 240px; overflow-y: auto; padding: 6px; }
.sh-dropdown-list .history-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; color: #94a3b8; transition: background .15s, color .15s; }
.sh-dropdown-list .history-item:hover { background: #2d3149; color: #e2e8f0; }
.sh-empty { padding: 20px; text-align: center; color: #475569; font-size: 12px; }

.store-area { display: flex; gap: 8px; flex-shrink: 0; }
.store-area textarea { flex: 1; background: #1a1d27; border: 1px solid #2d3149; border-radius: 8px; color: #e2e8f0; padding: 10px 14px; font-size: 14px; outline: none; resize: none; height: 60px; font-family: inherit; transition: border-color .2s; }
.store-area textarea:focus { border-color: #7c3aed; }

.organize-toolbar { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.organize-select { background: #1a1d27; border: 1px solid #2d3149; color: #e2e8f0; padding: 8px 12px; border-radius: 8px; font-size: 13px; outline: none; }

.memory-list-container { flex: 1; overflow-y: auto; min-height: 0; position: relative; }
.memory-list { display: flex; flex-direction: column; gap: 8px; min-height: 0; }

.btn { padding: 9px 14px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity .2s, transform .1s; }
.btn:active { transform: scale(.98); }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover { opacity: .85; }
.btn-accent { background: #10b981; color: #fff; }
.btn-accent:hover { opacity: .85; }
.btn-sm { padding: 6px 12px; font-size: 12px; }
.btn-secondary-sm { padding: 6px 12px; font-size: 12px; background: #1e293b; color: #94a3b8; border: 1px solid #2d3149; border-radius: 6px; cursor: pointer; }
.btn-secondary-sm:hover { border-color: #475569; }

.memory-card { background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 14px 16px; display: flex; align-items: flex-start; gap: 12px; transition: border-color .2s; }
.memory-card:hover { border-color: #7c3aed44; }
.memory-card.search-result { border-color: #7c3aed66; }
.memory-content { flex: 1; min-width: 0; }
.memory-text { font-size: 14px; color: #e2e8f0; line-height: 1.5; word-break: break-all; }
.memory-meta { margin-top: 6px; display: flex; align-items: center; gap: 10px; }
.memory-time { font-size: 11px; color: #64748b; }
.memory-score { font-size: 11px; background: #7c3aed22; color: #a78bfa; padding: 1px 7px; border-radius: 99px; font-weight: 600; }
.memory-id { font-size: 10px; color: #374151; font-family: monospace; }
.del-btn { background: none; border: none; color: #374151; cursor: pointer; font-size: 16px; padding: 2px 6px; border-radius: 4px; transition: color .2s, background .2s; flex-shrink: 0; }
.del-btn:hover { color: #ef4444; background: #ef444420; }

.empty { text-align: center; padding: 60px 20px; color: #64748b; }
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
.search-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 40px; color: #64748b; font-size: 14px; }
.spinner { width: 18px; height: 18px; border: 2px solid #2d3149; border-top-color: #7c3aed; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.btn-icon-sm { background: none; border: 1px solid #2d3149; color: #94a3b8; cursor: pointer; font-size: 13px; padding: 4px 9px; border-radius: 6px; transition: all .2s; flex-shrink: 0; }
.btn-icon-sm:hover { color: #e2e8f0; border-color: #475569; }
.btn:disabled { opacity: .5; cursor: not-allowed; }

.organize-groups, .organize-refined { display: flex; flex-direction: column; gap: 10px; }
.organize-group-card { background: #1a1d27; border: 1px solid #2d3149; border-radius: 8px; padding: 12px; }
.organize-group-card .og-label { font-size: 11px; color: #64748b; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; }
.organize-group-card .og-item { font-size: 13px; color: #e2e8f0; padding: 4px 0; border-bottom: 1px solid #12141c; display: flex; gap: 8px; }
.organize-group-card .og-item:last-child { border-bottom: none; }
.og-idx { color: #64748b; font-size: 11px; font-weight: 600; min-width: 18px; flex-shrink: 0; }
.og-refine-btn { font-size: 11px; padding: 3px 10px; }
.organize-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 8px 0; }
.organize-header > span { font-size: 14px; font-weight: 600; color: #a78bfa; }
.organize-actions { display: flex; align-items: center; gap: 8px; }
.og-refine-result { margin-top: 8px; }
.og-refine-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; }
.organize-group-card.og-applied { opacity: 0.5; }
.organize-group-card.og-applied .og-item { text-decoration: line-through; }
.og-refine-divider { border-top: 1px dashed #2d3149; margin: 8px 0; }
.og-refine-label { font-size: 11px; font-weight: 600; color: #10b981; margin-bottom: 4px; }
.og-refine-label:not(.refined) { color: #f59e0b; }
.organize-refined-text { background: #0f1117; border: 1px solid #2d3149; border-radius: 6px; padding: 8px 10px; font-size: 13px; color: #e2e8f0; line-height: 1.5; min-height: 40px; }
.organize-refined-text[contenteditable]:focus { border-color: #7c3aed; outline: none; }
.organize-category { font-size: 11px; color: #a78bfa; margin-top: 4px; }
.organize-check { display: flex; align-items: center; gap: 6px; padding: 4px 0; }
.organize-check input { width: auto; }
.organize-check label { font-size: 12px; color: #94a3b8; cursor: pointer; }
.organize-loading { text-align: center; padding: 40px; color: #64748b; font-size: 14px; }
.organize-footer-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid #2d3149; margin-top: 8px; position: sticky; bottom: 0; background: #0f1117; }
.organize-footer-stat { font-size: 13px; color: #a78bfa; font-weight: 600; }
</style>
