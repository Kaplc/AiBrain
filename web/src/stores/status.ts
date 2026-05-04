import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'

export const useStatusStore = defineStore('status', () => {
  const { fetchJson } = useApi()

  const modelLoaded = ref(false)
  const qdrantReady = ref(false)
  const device = ref<'cuda' | 'cpu'>('cpu')
  const flaskPid = ref<number | null>(null)
  const flaskPort = ref<number | null>(null)
  const flaskUptime = ref(0)
  const flaskReload = ref(false)
  const embeddingModel = ref('')
  const embeddingDim = ref(1024)
  const modelSize = ref('')
  const qdrantHost = ref('localhost')
  const qdrantPort = ref(6333)
  const qdrantCollection = ref('memories')
  const qdrantStoragePath = ref('storage')
  const qdrantTopK = ref(5)
  const qdrantDiskSize = ref(0)

  async function fetchStatus() {
    try {
      const d = await fetchJson<any>('/statusbar/api')
      modelLoaded.value = d.model_loaded ?? false
      qdrantReady.value = d.qdrant_ready ?? false
      device.value = d.device ?? 'cpu'
      flaskPid.value = d.flask_pid ?? null
      flaskPort.value = d.flask_port ?? null
      flaskUptime.value = d.flask_uptime ?? 0
      flaskReload.value = d.flask_reload ?? false
      embeddingModel.value = d.embedding_model ?? ''
      embeddingDim.value = d.embedding_dim ?? 1024
      modelSize.value = d.model_size ?? ''
      qdrantHost.value = d.qdrant_host ?? 'localhost'
      qdrantPort.value = d.qdrant_port ?? 6333
      qdrantCollection.value = d.qdrant_collection ?? 'memories'
      qdrantStoragePath.value = d.qdrant_storage_path ?? 'storage'
      qdrantTopK.value = d.qdrant_top_k ?? 5
      qdrantDiskSize.value = d.qdrant_disk_size ?? 0
    } catch {
      // 请求失败时保持上次状态
    }
  }

  return {
    modelLoaded, qdrantReady, device,
    flaskPid, flaskPort, flaskUptime, flaskReload,
    embeddingModel, embeddingDim, modelSize,
    qdrantHost, qdrantPort, qdrantCollection,
    qdrantStoragePath, qdrantTopK, qdrantDiskSize,
    fetchStatus,
  }
})
