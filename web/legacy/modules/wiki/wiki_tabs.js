/* 右侧面板 Tab 管理器 */
var WikiTabManager = null;

(function() {
  /* ========== StatsTab ========== */
  class StatsTab {
    constructor() {
      this.id = 'sidePanelStats';
    }
    onShow() {
      // 统计数据随文件列表更新，依赖 loadWikiData 中的统计面板更新逻辑
    }
  }

  /* ========== OpsTab ========== */
  class OpsTab {
    constructor() {
      this.id = 'sidePanelOps';
      this._pollTimer = null;
    }
    onShow() {
      this.restoreIndexProgress();
    }
    onHide() {
      this.stopPoll();
    }

    async restoreIndexProgress() {
      try {
        var pdata = await fetchJson(API + '/wiki/index-progress');
        if (pdata.status === 'running') {
          this._showProgress(pdata);
          this._startPoll();
        } else {
          this._showDone(pdata);
        }
      } catch (e) {
        console.error('[wiki] restoreIndexProgress error:', e);
      }
    }

    _showProgress(pdata) {
      var btn = document.getElementById('btnReindex');
      var progWrap = document.getElementById('indexProgressWrap');
      var progLabel = document.getElementById('indexProgressLabel');
      var progFill = document.getElementById('indexProgressFill');
      var progPct = document.getElementById('indexProgressPct');
      if (btn) { btn.disabled = true; btn.textContent = '索引中...'; }
      if (progWrap) progWrap.style.display = 'block';
      var pct = pdata.total > 0 ? Math.round((pdata.done / pdata.total) * 100) : 0;
      if (progFill) progFill.style.width = pct + '%';
      if (progPct) progPct.textContent = pct + '%';
      if (progLabel) progLabel.textContent = (pdata.current_file || '进行中...') + ' (' + pdata.done + '/' + pdata.total + ')';
      _lastIndexDone = pdata.done;
    }

    _showDone(pdata) {
      var btn = document.getElementById('btnReindex');
      var progWrap = document.getElementById('indexProgressWrap');
      var progFill = document.getElementById('indexProgressFill');
      var progPct = document.getElementById('indexProgressPct');
      var resultDiv = document.getElementById('indexResult');
      if (progFill) progFill.style.width = '100%';
      if (progPct) progPct.textContent = '100%';
      if (progWrap) progWrap.style.display = 'none';
      if (btn) { btn.disabled = false; btn.textContent = '重建索引'; }
      if (resultDiv) resultDiv.innerHTML = pdata.status === 'done'
        ? '<div class="index-result ok">索引完成</div>'
        : '<div class="index-result err">索引出错</div>';
    }

    _startPoll() {
      if (this._pollTimer) return;
      var self = this;
      this._pollTimer = setInterval(async function() {
        try {
          var pdata = await fetchJson(API + '/wiki/index-progress');
          if (pdata.status === 'running') {
            self._showProgress(pdata);
            await self._refreshLog();
          } else {
            self._showDone(pdata);
            self.stopPoll();
          }
        } catch (e) {
          console.error('[wiki] index poll error:', e);
        }
      }, 500);
    }

    stopPoll() {
      if (this._pollTimer) {
        clearInterval(this._pollTimer);
        this._pollTimer = null;
      }
    }

    async _refreshLog() {
      try {
        var container = document.getElementById('indexLogWrap');
        if (!container) return;
        var data = await fetchJson(API + '/wiki/index-log?lines=20');
        if (!data.lines) return;
        var html = data.lines.map(function(line) {
          return '<div class="log-line">' + escHtml(line) + '</div>';
        }).join('');
        container.innerHTML = html;
        container.scrollTop = container.scrollHeight;
      } catch (e) {
        // 日志获取失败不阻塞
      }
    }
  }

  /* ========== SettingsTab ========== */
  class SettingsTab {
    constructor() {
      this.id = 'sidePanelSettings';
    }
    onShow() {
      loadWikiSettingsData();
    }
  }

  /* ========== TabManager ========== */
  WikiTabManager = function() {
    this.tabs = {
      stats: new StatsTab(),
      ops: new OpsTab(),
      settings: new SettingsTab(),
    };
    this._currentTab = 'stats';
  };

  WikiTabManager.prototype.switchTo = function(tab) {
    var t = this.tabs[tab];
    if (!t) return;
    // hide current
    var cur = this.tabs[this._currentTab];
    if (cur && cur.onHide) cur.onHide();
    // switch
    document.querySelectorAll('.side-tab-btn').forEach(function(btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
    });
    document.querySelectorAll('.side-panel').forEach(function(panel) {
      panel.classList.remove('active');
    });
    var panel = document.getElementById('sidePanel' + tab.charAt(0).toUpperCase() + tab.slice(1));
    if (panel) panel.classList.add('active');
    this._currentTab = tab;
    if (t.onShow) t.onShow();
  };

  WikiTabManager.prototype.stopAll = function() {
    var ops = this.tabs.ops;
    if (ops && ops.stopPoll) ops.stopPoll();
  };
})();
