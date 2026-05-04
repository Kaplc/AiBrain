<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const navItems = [
  { name: 'overview', label: '总览' },
  { name: 'memory', label: '记忆' },
  { name: 'stream', label: '流' },
  { name: 'wiki', label: 'Wiki' },
  { name: 'logs', label: '日志' },
  { name: 'settings', label: '设置' },
]

function openInBrowser() {
  if ((window as any).pywebview?.api) {
    ;(window as any).pywebview.api.open_in_browser()
  } else {
    window.open(window.location.href, '_blank')
  }
}
</script>

<template>
  <nav class="nav-sidebar">
    <div class="nav-logo" @click="openInBrowser" title="在浏览器中打开">M</div>
    <div class="nav-items">
      <button
        v-for="item in navItems"
        :key="item.name"
        class="nav-item"
        :class="{ active: route.name === item.name }"
        @click="router.push({ name: item.name })"
      >
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.nav-sidebar {
  width: 80px;
  background: #1a1d27;
  border-right: 1px solid #2d3149;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
  flex-shrink: 0;
}
.nav-logo {
  font-size: 16px; font-weight: 700; color: #a78bfa;
  margin-bottom: 24px; cursor: pointer; border-radius: 8px;
  padding: 6px 4px; transition: background .2s;
}
.nav-logo:hover { background: #7c3aed22; }
.nav-items { display: flex; flex-direction: column; gap: 6px; flex: 1; width: 100%; padding: 0 10px; }
.nav-item {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 4px; border: none; border-radius: 8px;
  background: transparent; color: #64748b; font-size: 11px;
  cursor: pointer; transition: all .2s; width: 100%;
}
.nav-item:hover { background: #1e293b; color: #94a3b8; }
.nav-item.active { background: #7c3aed22; color: #a78bfa; }
.nav-label { font-weight: 600; }
</style>
