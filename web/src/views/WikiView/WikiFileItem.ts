export interface ApiWikiFile {
  filename: string
  abs_path: string
  rel_path?: string
  size_bytes: number
  modified: number
  preview: string
  index_status: 'synced' | 'out_of_sync' | 'not_indexed'
}

export class WikiFileItem {
  readonly filename: string
  readonly abs_path: string
  readonly rel_path: string
  readonly size_bytes: number
  readonly modified: number
  readonly preview: string
  index_status: 'synced' | 'out_of_sync' | 'not_indexed'
  isCurrent = false

  constructor(file: ApiWikiFile) {
    this.filename = file.filename
    this.abs_path = file.abs_path
    this.rel_path = file.rel_path || this._guessRelPath(file.abs_path, file.filename)
    this.size_bytes = file.size_bytes
    this.modified = file.modified
    this.preview = file.preview
    this.index_status = file.index_status
  }

  private _guessRelPath(absPath: string, filename: string): string {
    const idx = absPath.lastIndexOf(filename)
    return idx > 0 ? absPath.slice(idx) : filename
  }

  markSynced(): void {
    this.index_status = 'synced'
    this.isCurrent = false
  }

  markCurrent(): void {
    this.isCurrent = true
  }
}
