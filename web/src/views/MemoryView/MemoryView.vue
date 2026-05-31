<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { memoryViewModel } from './index'
import SearchPanel from './SearchTab/SearchPanel.vue'
import StorePanel from './StoreTab/StorePanel.vue'
import OrganizePanel from './OrganizeTab/OrganizePanel.vue'
import MemorySettingsPanel from './SettingsTab/MemorySettingsPanel.vue'
import GraphPanel from './GraphTab/GraphPanel.vue'
import EntityPanel from './EntityTab/EntityPanel.vue'

onMounted(() => memoryViewModel.onMounted())
onUnmounted(() => memoryViewModel.onUnmounted())
</script>

<template>
  <div class="memory-layout">
    <nav class="memory-nav">
      <div class="nav-tabs">
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'search' }" @click="memoryViewModel.switchTab('search')">搜索记忆</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'store' }" @click="memoryViewModel.switchTab('store')">保存记忆</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'organize' }" @click="memoryViewModel.switchTab('organize')">合并记忆</button>
        <button class="nav-tab nav-tab-settings" :class="{ active: memoryViewModel.currentTab.value === 'settings' }" @click="memoryViewModel.switchTab('settings')" title="记忆设置">⚙ 设置</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'graph' }" @click="memoryViewModel.switchTab('graph')">图谱</button>
        <button class="nav-tab" :class="{ active: memoryViewModel.currentTab.value === 'entity' }" @click="memoryViewModel.switchTab('entity')">实体</button>
      </div>
      <div class="nav-stat">
        <span class="stat-value">{{ memoryViewModel.animatingCount.value }}</span>
        <span class="stat-label">条记忆</span>
        <button class="btn-icon" @click="memoryViewModel.loadAll()" title="刷新">↻</button>
      </div>
    </nav>

    <SearchPanel v-show="memoryViewModel.currentTab.value === 'search'" />
    <StorePanel v-show="memoryViewModel.currentTab.value === 'store'" />
    <OrganizePanel v-show="memoryViewModel.currentTab.value === 'organize'" />
    <MemorySettingsPanel v-show="memoryViewModel.currentTab.value === 'settings'" />
    <GraphPanel v-show="memoryViewModel.currentTab.value === 'graph'" />
    <EntityPanel v-show="memoryViewModel.currentTab.value === 'entity'" />
  </div>
</template>

<style scoped>
.memory-layout { display: flex; flex-direction: column; padding: 20px 24px; overflow: hidden; flex: 1; min-height: 0; box-sizing: border-box; height: 100%; gap: 16px; }
.memory-nav { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.nav-tabs { display: flex; gap: 4px; background: #1a1d27; border-radius: 10px; padding: 4px; }
.nav-tab { padding: 8px 20px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; color: #94a3b8; background: transparent; transition: all .2s; }
.nav-tab:hover { color: #e2e8f0; }
.nav-tab.active { background: #7c3aed; color: #fff; }
.nav-tab-settings { color: #64748b; font-size: 12px; padding: 8px 14px; }
.nav-tab-settings:hover { color: #94a3b8; }
.nav-tab-settings.active { background: #1e293b; color: #a78bfa; }
.nav-stat { display: flex; align-items: center; gap: 8px; }
.nav-stat .stat-value { font-size: 18px; font-weight: 700; color: #a78bfa; }
.nav-stat .stat-label { font-size: 12px; color: #64748b; }
.btn-icon { background: none; border: 1px solid #2d3149; color: #94a3b8; cursor: pointer; font-size: 14px; padding: 4px 10px; border-radius: 6px; transition: all .2s; }
.btn-icon:hover { color: #e2e8f0; border-color: #475569; }

/* OrganizePanel styles */
.tab-panel { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.organize-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.organize-select { background: #1e2235; color: #e2e8f0; border: 1px solid #2d3149; border-radius: 6px; padding: 6px 12px; font-size: 13px; cursor: pointer; }
.organize-select:focus { outline: none; border-color: #7c3aed; }
.btn { padding: 6px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.btn-accent { background: #7c3aed; color: #fff; }
.btn-accent:hover { background: #6d28d9; }
.btn-warn { background: #f59e0b; color: #fff; }
.btn-warn:hover { background: #d97706; }
.btn-danger-sm { background: #ef4444; color: #fff; padding: 4px 12px; font-size: 12px; }
.btn-danger-sm:hover { background: #dc2626; }
.memory-list-container { flex: 1; overflow: auto; }
.organize-loading { text-align: center; padding: 40px; color: #94a3b8; font-size: 14px; }
.organize-header { padding: 8px 0 12px; font-size: 13px; color: #94a3b8; }
.organize-groups { display: flex; flex-direction: column; gap: 12px; }
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; color: #64748b; }
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
