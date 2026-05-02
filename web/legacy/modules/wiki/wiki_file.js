/* WikiFileList 类 - 左侧文件列表管理 */
var WikiFileList = null;

(function() {

  /* ========== WikiFile ========== */
  class WikiFile {
    constructor(data) {
      this.filename = data.filename || '';
      this.absPath = data.abs_path || '';
      this.sizeBytes = data.size_bytes || 0;
      this.modified = data.modified || 0;
      this.preview = data.preview || '';
      this.indexStatus = data.index_status || 'not_indexed';
    }

    icon() {
      if (this.indexStatus === 'synced') return '<span style="color:#22c55e" title="已同步">✓</span>';
      if (this.indexStatus === 'out_of_sync') return '<span style="color:#f97316" title="文件已修改，需重建索引">⚠</span>';
      return '<span style="color:#94a3b8" title="未索引">○</span>';
    }

    toRowHtml() {
      return '<tr onclick="copyPath(\'' + escAttr(this.absPath || this.filename) + '\', this)" style="cursor:pointer">'
        + '<td style="text-align:center">' + this.icon() + '</td>'
        + '<td class="ft-name">' + escHtml(this.filename) + '</td>'
        + '<td class="ft-meta">' + formatSize(this.sizeBytes) + '</td>'
        + '<td class="ft-meta">' + formatDate(this.modified) + '</td>'
        + '<td class="ft-preview" title="' + escAttr(this.preview) + '">' + escHtml(this.preview || '') + '</td>'
        + '</tr>';
    }

    /** 刷新表格中对应行的图标（外部传入状态） */
    updateIcon(indexStatus) {
      this.indexStatus = indexStatus;
      var rows = document.querySelectorAll('#wikiTableWrap tbody tr');
      for (var i = 0; i < rows.length; i++) {
        var nameCell = rows[i].querySelector('.ft-name');
        if (nameCell && nameCell.textContent.trim() === this.filename) {
          var iconTd = rows[i].querySelector('td:first-child');
          if (iconTd) iconTd.innerHTML = this.icon();
          break;
        }
      }
    }
  }

  /* ========== WikiFileList ========== */
  WikiFileList = function(initialFiles) {
    this.files = (initialFiles || []).map(function(d) { return new WikiFile(d); });
    this.sortKey = 'modified';
    this.sortAsc = false;
  };

  WikiFileList.prototype._sortFiles = function() {
    var key = this.sortKey;
    var asc = this.sortAsc;
    this.files.sort(function(a, b) {
      var va = a[key], vb = b[key];
      if (va == null) va = '';
      if (vb == null) vb = '';
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return asc ? -1 : 1;
      if (va > vb) return asc ? 1 : -1;
      return 0;
    });
  };

  WikiFileList.prototype.sortBy = function(key) {
    if (this.sortKey === key) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortKey = key;
      this.sortAsc = true;
    }
    this._sortFiles();
  };

  WikiFileList.prototype.setData = function(files) {
    this.files = (files || []).map(function(d) { return new WikiFile(d); });
    this._sortFiles();
  };

  WikiFileList.prototype.refreshStatus = function() {
    // 仅刷新已存在行的图标，不重渲染表格
    var rows = document.querySelectorAll('#wikiTableWrap tbody tr');
    for (var i = 0; i < rows.length; i++) {
      var nameCell = rows[i].querySelector('.ft-name');
      if (!nameCell) continue;
      var name = nameCell.textContent.trim();
      var file = this.files.find(function(f) { return f.filename === name; });
      if (file) {
        var iconTd = rows[i].querySelector('td:first-child');
        if (iconTd) iconTd.innerHTML = file.icon();
      }
    }
  };

  WikiFileList.prototype.render = function() {
    var wrap = document.getElementById('wikiTableWrap');
    if (!wrap) return;

    var arrow = function(key) {
      if (this.sortKey !== key) return '';
      return this.sortAsc ? ' ▲' : ' ▼';
    }.bind(this);

    var html = '<table class="file-table"><thead><tr>'
      + '<th style="width:40px"></th>'
      + '<th onclick="wikiFileList.sortBy(\'filename\')">文件名' + arrow('filename') + '</th>'
      + '<th onclick="wikiFileList.sortBy(\'sizeBytes\')">大小' + arrow('sizeBytes') + '</th>'
      + '<th onclick="wikiFileList.sortBy(\'modified\')">修改时间' + arrow('modified') + '</th>'
      + '<th>预览</th></tr></thead><tbody>';

    this.files.forEach(function(f) {
      html += f.toRowHtml();
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;
    var meta = document.getElementById('wikiFileListMeta');
    if (meta) meta.textContent = this.files.length + ' 个文件';
  };

  window.WikiFileList = WikiFileList;
  window.WikiFile = WikiFile;
})();
