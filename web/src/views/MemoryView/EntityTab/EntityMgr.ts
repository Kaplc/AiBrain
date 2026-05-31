import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { EntityMgrResponse, EntityListItem, LinkInfo } from './types'

export class EntityMgr {
  readonly loading = ref(false)
  readonly links = ref<LinkInfo[]>([])
  readonly entities = ref<EntityListItem[]>([])
  readonly total = ref(0)
  readonly page = ref(1)
  readonly pageSize = ref(20)
  readonly pages = ref(0)
  readonly hasPrev = ref(false)
  readonly hasNext = ref(false)
  readonly searchQuery = ref('')

  private api = useApi()

  async loadLinks() {
    this.loading.value = true
    try {
      const params: Record<string, string | number> = {
        page: this.page.value,
        page_size: this.pageSize.value,
      }
      if (this.searchQuery.value) params['search'] = this.searchQuery.value
      const data = await this.api.fetchJson<EntityMgrResponse>('/memory/entity/entitymgr', { query: params })
      this.links.value = data.links ?? []
      this.total.value = data.total ?? 0
      this.pages.value = data.pages ?? 1
      this.hasPrev.value = this.page.value > 1
      this.hasNext.value = this.page.value < this.pages.value
    } catch {
      this.links.value = []
    } finally {
      this.loading.value = false
    }
  }

  async loadEntities() {
    try {
      const data = await this.api.fetchJson<{ entities: EntityListItem[] }>('/memory/graph/entities', { method: 'POST', body: '{}' })
      this.entities.value = data.entities ?? []
    } catch {
      this.entities.value = []
    }
  }

  async handleSubmit(entityA: string, entityB: string) {
    await this.api.fetchJson('/memory/entity/entitymgr', {
      method: 'POST',
      body: JSON.stringify({ entity_a: entityA, entity_b: entityB }),
    })
  }

  nextPage() {
    if (this.hasNext.value) { this.page.value++; this.loadLinks() }
  }

  prevPage() {
    if (this.hasPrev.value) { this.page.value--; this.loadLinks() }
  }
}