import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

export interface GraphNode {
  id: string
  label: string
  type: string
  memoryCount: number
}

export interface GraphEdge {
  source: string
  target: string
  relationType: string
  weight: number
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export class GraphTab {
  readonly loading = ref(false)
  readonly graphData = ref<GraphData>({ nodes: [], edges: [] })

  private _api = useApi()
  private _toast = useToast()

  async loadGraph(): Promise<void> {
    this.loading.value = true
    try {
      const data = await this._api.postJson<GraphData>('/memory/graph/visualization', {})
      this.graphData.value = data
    } catch (e: any) {
      this._toast.show('加载图谱失败: ' + e.message)
    } finally {
      this.loading.value = false
    }
  }
}
