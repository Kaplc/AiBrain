import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

export interface EntityStats {
  entity_nodes: number
  mentions: number
  memory_relations: number
  typed_entity_relations: number
  entity_relations: number
  graph_loaded: boolean
  graph_nodes: number
  graph_edges: number
}

export class EntityTab {
  readonly loading = ref(false)
  readonly stats = ref<EntityStats>({
    entity_nodes: 0,
    mentions: 0,
    memory_relations: 0,
    typed_entity_relations: 0,
    entity_relations: 0,
    graph_loaded: false,
    graph_nodes: 0,
    graph_edges: 0,
  })

  private _api = useApi()
  private _toast = useToast()

  async loadStats(): Promise<void> {
    this.loading.value = true
    try {
      const data = await this._api.fetchJson<EntityStats>('/memory/entity/stats')
      this.stats.value = data
    } catch (e: any) {
      this._toast.show('加载实体统计失败: ' + e.message)
    } finally {
      this.loading.value = false
    }
  }
}