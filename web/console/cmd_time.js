/* ==================== 时间命令 ==================== */
// 命令：time - 显示当前时间

registerCommand('time', function(cmd) {
  const now = new Date();
  const timeStr = now.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    weekday: 'long'
  });
  logToConsole('═══════════════════════════════', 'info');
  logToConsole(`  当前时间: ${timeStr}`, 'success');
  logToConsole('═══════════════════════════════', 'info');
}, '显示当前日期和时间');