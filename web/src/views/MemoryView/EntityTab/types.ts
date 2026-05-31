/* EntityMgr types */

export interface LinkInfo {
  entity_a: string
  entity_b: string
}

export interface EntityMgrResponse {
  links: LinkInfo[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface EntityListItem {
  name: string
  memory_count: number
}