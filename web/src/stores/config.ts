import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'

export interface AibrainConfigSection {
  fields: ConfigField[]
}

export interface ConfigField {
  key: string
  label: string
  type: 'text' | 'number' | 'password' | 'dir'
  value: any
  default: any
}

export const useConfigStore = defineStore('config', () => {
  const { fetchJson, postJson } = useApi()

  const device = ref<'cuda' | 'cpu'>('cpu')
  const savedDevice = ref<'cuda' | 'cpu'>('cpu')
  const aibrainConfig = ref<any>(null)

  async function loadConfig() {
    try {
      const [cfg, st, aibrain] = await Promise.all([
        fetchJson<any>('/settings/api'),
        fetchJson<any>('/statusbar/api'),
        fetchJson<any>('/settings/aibrain-config'),
      ])
      savedDevice.value = cfg.device ?? 'cpu'
      device.value = savedDevice.value
      aibrainConfig.value = aibrain
      return { cfg, st, aibrain }
    } catch (e) {
      console.error('[configStore] loadConfig error:', e)
      return null
    }
  }

  async function applyDeviceChange() {
    if (device.value === savedDevice.value) return false
    try {
      await postJson('/settings/reload-model', { device: device.value })
      savedDevice.value = device.value
      return true
    } catch (e) {
      console.error('[configStore] applyDeviceChange error:', e)
      return false
    }
  }

  async function saveAibrainConfig(section: string, data: Record<string, any>) {
    try {
      const r = await postJson<any>('/settings/save-aibrain-config', { [section]: data })
      return r.error ? false : true
    } catch {
      return false
    }
  }

  return {
    device, savedDevice, aibrainConfig,
    loadConfig, applyDeviceChange, saveAibrainConfig,
  }
})
