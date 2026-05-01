/* WikiFile 类 - 表示单个 wiki 文件 */

class WikiFile {
  constructor(data) {
    this.filename = data.filename || '';
    this.absPath = data.abs_path || '';
    this.sizeBytes = data.size_bytes || 0;
    this.modified = data.modified || 0;
    this.preview = data.preview || '';
    this.indexStatus = data.index_status || 'not_indexed';
  }

  /** 索引状态图标（HTML） */
  icon() {
    if (this.indexStatus === 'synced') return '<span style="color:#22c55e" title="已同步">✓</span>';
    if (this.indexStatus === 'out_of_sync') return '<span style="color:#f97316" title="文件已修改，需重建索引">⚠</span>';
    return '<span style="color:#94a3b8" title="未索引">○</span>';
  }

  /** 转为 <tr> HTML */
  toRowHtml() {
    return '<tr onclick="copyPath(\'' + escAttr(this.absPath || this.filename) + '\', this)" style="cursor:pointer">'
      + '<td style="text-align:center">' + this.icon() + '</td>'
      + '<td class="ft-name">' + escHtml(this.filename) + '</td>'
      + '<td class="ft-meta">' + formatSize(this.sizeBytes) + '</td>'
      + '<td class="ft-meta">' + formatDate(this.modified) + '</td>'
      + '<td class="ft-preview" title="' + escAttr(this.preview) + '">' + escHtml(this.preview || '') + '</td>'
      + '</tr>';
  }
}

function _createWikiFiles(files) {
  return files.map(function(d) { return new WikiFile(d); });
}