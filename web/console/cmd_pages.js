/* ==================== 页面命令 ==================== */
// 命令：pages - 列出可用页面

registerCommand('pages', function(cmd) {
  const pages = [
    { name: 'overview', desc: '总览' },
    { name: 'memory', desc: '记忆' },
    { name: 'steam', desc: '流' },
    { name: 'wiki', desc: 'Wiki' },
    { name: 'logs', desc: '日志' },
    { name: 'settings', desc: '设置' }
  ];

  logToConsole('可用页面：', 'info');
  pages.forEach(p => {
    const marker = p.name === currentPage ? ' ◄' : '';
    logToConsole(`  ${p.name.padEnd(10)} - ${p.desc}${marker}`, p.name === currentPage ? 'success' : 'info');
  });
}, '列出所有页面');

/* ==================== 刷新命令 ==================== */
// 命令：reload - 刷新当前页面

registerCommand('reload', function(cmd) {
  logToConsole('刷新页面...', 'info');
  loadPage(currentPage, true);
  logToConsole('刷新完成', 'success');
}, '刷新当前页面');

/* ==================== 打开页面命令 ==================== */
// 命令：open <page> - 打开指定页面

registerCommand('open', function(cmd) {
  // 提取页面名（去掉 "open " 前缀）
  const page = cmd.slice(5).trim().toLowerCase();

  if (!page) {
    logToConsole('请指定页面名，例如: open memory', 'warn');
    logToConsole('使用 pages 命令查看可用页面', 'info');
    return;
  }

  // 检查页面是否存在
  const validPages = ['overview', 'memory', 'steam', 'wiki', 'logs', 'settings'];
  if (!validPages.includes(page)) {
    logToConsole(`未知页面: ${page}`, 'error');
    logToConsole('使用 pages 命令查看可用页面', 'info');
    return;
  }

  logToConsole(`正在打开页面: ${page}...`, 'info');
  loadPage(page);
  logToConsole(`已切换到: ${page}`, 'success');
}, '打开指定页面');