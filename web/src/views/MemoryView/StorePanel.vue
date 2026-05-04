<script setup lang="ts">
import { memoryViewModel } from './index'

const vm = memoryViewModel
</script>

<template>
  <div class="tab-panel">
    <div class="store-area">
      <textarea
        v-model="vm.storeTab.input.value"
        placeholder="输入要记住的内容..."
        @keydown.ctrl.enter="vm.storeTab.save()"
      ></textarea>
      <button class="btn btn-primary" @click="vm.storeTab.save()">保存记忆</button>
    </div>
    <div class="memory-list-container">
      <div class="memory-list">
        <template v-if="vm.storeTab.memories.value.length">
          <div v-for="m in vm.storeTab.memories.value" :key="m.id" class="memory-card">
            <div class="memory-content">
              <div class="memory-text">{{ m.text }}</div>
              <div class="memory-meta">
                <span class="memory-time">{{ vm.storeTab.formatTime(m.timestamp) }}</span>
                <span class="memory-id">{{ (m.id || '').slice(0, 8) }}...</span>
              </div>
            </div>
            <button class="del-btn" @click="vm.storeTab.delete(m.id)" title="删除">✕</button>
          </div>
        </template>
        <div v-else class="empty">
          <div class="empty-icon">🧠</div>
          <div class="empty-text">还没有任何记忆</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.store-area { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.store-area textarea { background: #1e2235; color: #e2e8f0; border: 1px solid #2d3149; border-radius: 6px; padding: 10px 12px; font-size: 13px; resize: none; min-height: 80px; font-family: inherit; }
.store-area textarea:focus { outline: none; border-color: #7c3aed; }
.store-area textarea::placeholder { color: #64748b; }
.btn { padding: 6px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-primary:hover { background: #6d28d9; }
.memory-list-container { flex: 1; overflow: auto; }
.memory-list { display: flex; flex-direction: column; gap: 8px; }
.memory-card { background: #1e2235; border-radius: 8px; padding: 12px; display: flex; gap: 12px; }
.memory-content { flex: 1; min-width: 0; }
.memory-text { font-size: 13px; color: #e2e8f0; line-height: 1.5; word-break: break-word; }
.memory-meta { display: flex; gap: 12px; margin-top: 6px; font-size: 11px; color: #64748b; }
.del-btn { background: none; border: none; color: #64748b; cursor: pointer; font-size: 14px; padding: 4px; }
.del-btn:hover { color: #ef4444; }
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; color: #64748b; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
