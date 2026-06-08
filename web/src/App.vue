<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import NavSidebar from './components/NavSidebar.vue'
import StatusBar from './components/StatusBar.vue'
import ConsolePanel from './components/ConsolePanel.vue'
import { toggleConsole } from '@/composables/useConsoleState'
import { useToast } from '@/composables/useToast'

const toast = useToast()

function handleGlobalKeydown(e: KeyboardEvent) {
  // ~ 键打开/关闭控制台
  if (e.key === '`' || e.key === '~') {
    e.preventDefault()
    toggleConsole()
  }
  // F5 刷新
  if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
    e.preventDefault()
    window.location.reload()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <div class="app">
    <NavSidebar />
    <main class="main-content">
      <div id="page-content">
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="['ChatView']">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </div>
      <StatusBar />
    </main>
  </div>
  <ConsolePanel />
  <div class="toast" :class="[toast.type.value, { show: toast.visible.value }]">{{ toast.message.value }}</div>
</template>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', sans-serif;
  background: #0f1117;
  color: #e2e8f0;
  height: 100vh;
  overflow: hidden;
}
.app { display: flex; height: 100vh; }
.main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
#page-content { flex: 1; min-height: 0; overflow-y: auto; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2d3149; border-radius: 2px; }
* { scrollbar-width: thin; scrollbar-color: #2d3149 transparent; }

.toast {
  position: fixed; bottom: 24px; right: 24px;
  background: #1a1d27; border: 1px solid #2d3149; border-radius: 10px;
  padding: 12px 18px; font-size: 13px;
  box-shadow: 0 8px 32px #0008;
  opacity: 0; transform: translateY(12px);
  transition: all .3s; pointer-events: none;
  z-index: 999; max-width: 300px;
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-color: #22c55e44; color: #86efac; }
.toast.error { border-color: #ef444444; color: #fca5a5; }
</style>
