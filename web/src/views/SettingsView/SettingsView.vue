<script setup lang="ts">
import { onMounted, nextTick } from 'vue'
import { settingsViewModel } from './index'

onMounted(async () => {
  console.log('[SettingsView] mounted')
  await settingsViewModel.onMounted()
  await nextTick()
  settingsViewModel.initDirChecks()
})
</script>

<template>
  <div class="settings-wrap">
    <div class="settings-header">
      <div class="settings-title">设置</div>
    </div>

    <div class="config-tabs">
      <button
        v-for="tab in settingsViewModel.tabList"
        :key="tab.name"
        class="tab-btn"
        :class="{ active: settingsViewModel.activeTab.value === tab.name }"
        @click="settingsViewModel.switchTab(tab.name)"
      >{{ tab.title }}</button>
    </div>

    <template v-for="tab in settingsViewModel.tabList" :key="tab.name">
      <component :is="tab.component" v-if="settingsViewModel.activeTab.value === tab.name" />
    </template>
  </div>
</template>

<style scoped>
.settings-wrap { padding: 24px; display: flex; flex-direction: column; gap: 16px; box-sizing: border-box; flex: 1; }
.settings-header { display: flex; align-items: center; justify-content: space-between; }
.settings-title { font-size: 18px; font-weight: 700; }
.config-tabs { display: flex; gap: 8px; background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px; padding: 8px; }
.tab-btn { flex: 1; padding: 8px 16px; background: transparent; border: none; border-radius: 6px; color: #94a3b8; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.tab-btn:hover { color: #e2e8f0; background: #2d3149; }
.tab-btn.active { color: #fff; background: #7c3aed; }
</style>
