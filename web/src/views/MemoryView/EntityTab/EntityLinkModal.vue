<script setup lang="ts">
import { ref, watch } from 'vue'
import { useApi } from '@/composables/useApi'

const props = defineProps<{
  visible: boolean
  prefillA?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const api = useApi()
const entityA = ref('')
const entityB = ref('')
const suggestionsA = ref<string[]>([])
const suggestionsB = ref<string[]>([])
const loadingA = ref(false)
const loadingB = ref(false)
const submitting = ref(false)
let searchTimerA: ReturnType<typeof setTimeout> | null = null
let searchTimerB: ReturnType<typeof setTimeout> | null = null

watch(() => props.visible, v => {
  if (v) {
    if (props.prefillA) entityA.value = props.prefillA
  } else {
    entityA.value = ''
    entityB.value = ''
    suggestionsA.value = []
    suggestionsB.value = []
  }
})

watch(entityA, val => {
  if (searchTimerA) clearTimeout(searchTimerA)
  if (!val) { suggestionsA.value = []; return }
  searchTimerA = setTimeout(() => searchEntities(val, 'A'), 300)
})

watch(entityB, val => {
  if (searchTimerB) clearTimeout(searchTimerB)
  if (!val) { suggestionsB.value = []; return }
  searchTimerB = setTimeout(() => searchEntities(val, 'B'), 300)
})

async function searchEntities(query: string, target: 'A' | 'B') {
  if (target === 'A') loadingA.value = true
  else loadingB.value = true
  try {
    const data = await api.fetchJson<{ entities: { name: string }[] }>('/memory/graph/entities', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const filtered = (data.entities ?? [])
      .map(e => e.name)
      .filter(n => n.toLowerCase().includes(query.toLowerCase()))
      .slice(0, 8)
    if (target === 'A') suggestionsA.value = filtered
    else suggestionsB.value = filtered
  } catch {
    if (target === 'A') suggestionsA.value = []
    else suggestionsB.value = []
  } finally {
    if (target === 'A') loadingA.value = false
    else loadingB.value = false
  }
}

function pickA(name: string) {
  entityA.value = name
  suggestionsA.value = []
}

function pickB(name: string) {
  entityB.value = name
  suggestionsB.value = []
}

async function handleSubmit() {
  const a = entityA.value.trim()
  const b = entityB.value.trim()
  if (!a || !b) return
  submitting.value = true
  try {
    await api.fetchJson('/memory/entity/entitymgr', {
      method: 'POST',
      body: JSON.stringify({ entity_a: a, entity_b: b }),
    })
    emit('close')
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="emit('close')">
      <div class="modal">
        <div class="modal-header">
          <span class="modal-title">添加链接</span>
          <button class="btn-close" @click="emit('close')">×</button>
        </div>

        <div class="modal-body">
          <div class="field">
            <label class="field-label">实体 A</label>
            <div class="autocomplete-wrap">
              <input v-model="entityA" class="field-input" placeholder="输入实体名称..." autocomplete="off" />
              <div v-if="suggestionsA.length" class="suggestions">
                <div v-for="s in suggestionsA" :key="s" class="suggestion-item" @click="pickA(s)">{{ s }}</div>
              </div>
            </div>
          </div>

          <div class="field">
            <label class="field-label">实体 B</label>
            <div class="autocomplete-wrap">
              <input v-model="entityB" class="field-input" placeholder="输入实体名称..." autocomplete="off" />
              <div v-if="suggestionsB.length" class="suggestions">
                <div v-for="s in suggestionsB" :key="s" class="suggestion-item" @click="pickB(s)">{{ s }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-cancel" @click="emit('close')">取消</button>
          <button class="btn-submit" :disabled="!entityA.trim() || !entityB.trim() || submitting" @click="handleSubmit">
            {{ submitting ? '提交中...' : '确定' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.modal {
  background: #1a1d27;
  border: 1px solid rgba(100,120,200,0.2);
  border-radius: 12px;
  width: 420px;
  max-width: 90vw;
  overflow: hidden;
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(100,120,200,0.1);
}
.modal-title { font-size: 15px; font-weight: 600; color: #e2e8f0; }
.btn-close {
  background: none; border: none; color: #64748b; cursor: pointer;
  font-size: 20px; line-height: 1; padding: 0;
}
.btn-close:hover { color: #e2e8f0; }
.modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; color: #64748b; letter-spacing: 0.05em; }
.autocomplete-wrap { position: relative; }
.field-input {
  width: 100%; padding: 8px 12px;
  background: rgba(10,15,30,0.8);
  border: 1px solid rgba(100,140,220,0.2);
  border-radius: 8px;
  color: #e2e8f0; font-size: 13px; outline: none;
  box-sizing: border-box;
}
.field-input:focus { border-color: rgba(100,160,255,0.4); }
.suggestions {
  position: absolute; top: 100%; left: 0; right: 0;
  background: #1e2235;
  border: 1px solid rgba(100,120,200,0.2);
  border-radius: 8px;
  margin-top: 4px;
  max-height: 200px; overflow-y: auto;
  z-index: 10;
}
.suggestion-item {
  padding: 8px 12px; font-size: 13px; color: #94a3b8; cursor: pointer;
  transition: background 0.15s;
}
.suggestion-item:hover { background: rgba(80,100,160,0.2); color: #e2e8f0; }
.modal-footer {
  display: flex; gap: 10px; justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid rgba(100,120,200,0.1);
}
.btn-cancel {
  padding: 6px 16px; border-radius: 6px; border: 1px solid rgba(100,140,220,0.25);
  background: rgba(30,50,100,0.3); color: rgba(140,170,220,0.8);
  cursor: pointer; font-size: 13px;
}
.btn-cancel:hover { background: rgba(60,90,180,0.35); color: #c8d8f0; }
.btn-submit {
  padding: 6px 20px; border-radius: 6px; border: none;
  background: #7c3aed; color: #fff; cursor: pointer; font-size: 13px; font-weight: 600;
}
.btn-submit:hover:not(:disabled) { background: #6d28d9; }
.btn-submit:disabled { opacity: 0.4; cursor: not-allowed; }
</style>