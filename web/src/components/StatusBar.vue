<script setup lang="ts">
import { useStatusStore } from '@/stores/status'
import { usePolling } from '@/composables/usePolling'
import { ref } from 'vue'

const statusStore = useStatusStore()
const building = ref(false)
const buildMsg = ref('')
const buildFailed = ref(false)
console.log('[StatusBar] mounted, starting polling...')
const { start } = usePolling(() => statusStore.fetchStatus(), 3000)

statusStore.fetchStatus()
start()

async function triggerBuild() {
  if (building.value) return
  building.value = true
  buildMsg.value = '构建中...'
  buildFailed.value = false
  try {
    const res = await fetch('/overview/frontend/build', { method: 'POST' })
    const data = await res.json()
    console.log('[StatusBar] build result:', data)
    if (data.ok) {
      buildMsg.value = '构建成功'
      buildFailed.value = false
    } else {
      buildMsg.value = '构建失败'
      buildFailed.value = true
      console.error('[StatusBar] build failed:', data.error)
    }
  } catch (e) {
    buildMsg.value = '构建失败'
    buildFailed.value = true
    console.error('[StatusBar] build error:', e)
  }
  building.value = false
  setTimeout(() => { buildMsg.value = ''; buildFailed.value = false }, 3000)
}
</script>

<template>
  <div class="statusbar">
    <div class="statusbar-item">
      <span>{{ statusStore.modelLoaded ? '模型就绪' : '模型加载中' }}</span>
      <div
        class="statusbar-dot"
        :class="{
          ok: statusStore.modelLoaded,
          loading: !statusStore.modelLoaded,
        }"
      />
    </div>
    <div class="statusbar-item">
      <span>Qdrant</span>
      <div
        class="statusbar-dot"
        :class="{
          ok: statusStore.qdrantReady,
          err: !statusStore.qdrantReady,
        }"
      />
    </div>
    <div class="statusbar-item">
      <span>{{ statusStore.device === 'cuda' ? 'GPU' : 'CPU' }}</span>
    </div>
    <div class="statusbar-right">
      <span v-if="buildMsg" class="build-msg" :class="{ fail: buildFailed }">{{ buildMsg }}</span>
      <button v-else class="build-btn" @click="triggerBuild" title="构建前端">构建</button>
    </div>
  </div>
</template>

<style scoped>
.statusbar {
  height: 28px; background: #1a1d27; border-top: 1px solid #2d3149;
  display: flex; align-items: center; justify-content: flex-end;
  gap: 16px; padding: 0 16px; font-size: 11px; color: #64748b;
  flex-shrink: 0;
}
.statusbar-item { display: flex; align-items: center; gap: 5px; }
.statusbar-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  box-sizing: content-box; transform: none;
}
.statusbar-dot.ok {
  background: #22c55e; box-shadow: 0 0 5px #22c55e;
  animation: dot-pulse-ok 2s ease-in-out infinite;
}
.statusbar-dot.err {
  background: #ef4444; box-shadow: 0 0 4px #ef4444;
}
.statusbar-dot.loading {
  background: #eab308; box-shadow: 0 0 5px #eab308;
  animation: dot-pulse-loading 1s ease-in-out infinite;
}
@keyframes dot-pulse-ok {
  0%, 100% { opacity: 1; box-shadow: 0 0 5px #22c55e; }
  50% { opacity: 0.5; box-shadow: 0 0 2px #22c55e; }
}
@keyframes dot-pulse-loading {
  0%, 100% { opacity: 1; box-shadow: 0 0 5px #eab308; }
  50% { opacity: 0.5; box-shadow: 0 0 2px #eab308; }
}
.statusbar-right { display: flex; align-items: center; gap: 8px; margin-left: 8px; }
.build-btn {
  padding: 2px 10px; background: #7c3aed22; border: 1px solid #7c3aed44;
  border-radius: 4px; font-size: 10px; color: #a78bfa; cursor: pointer;
  transition: all .2s;
}
.build-btn:hover { background: #7c3aed44; color: #c4b5fd; }
.build-msg { font-size: 10px; color: #86efac; }
.build-msg.fail { color: #ef4444; }
</style>
