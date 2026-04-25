/* ==================== 状态命令 ==================== */
// 命令：status - 显示当前系统状态

registerCommand('status', function(cmd) {
  // 获取模型状态
  const sbModel = document.getElementById('sbModelText').textContent;
  const sbDevice = document.getElementById('sbDeviceText').textContent;

  // 输出状态信息
  logToConsole('═══════════════════════════════', 'info');
  logToConsole('         系统状态', 'info');
  logToConsole('═══════════════════════════════', 'info');
  logToConsole(`模型状态: ${sbModel}`, sbModel === '模型就绪' ? 'success' : 'warn');
  logToConsole(`运行设备: ${sbDevice}`, 'info');
  logToConsole(`当前页面: ${currentPage || 'unknown'}`, 'info');

  // 获取Qdrant状态
  const qdrantDot = document.getElementById('sbQdrantDot');
  const qdrantOk = qdrantDot && qdrantDot.classList.contains('ok');
  logToConsole(`Qdrant: ${qdrantOk ? '已连接' : '未连接'}`, qdrantOk ? 'success' : 'error');
  logToConsole('═══════════════════════════════', 'info');
}, '显示系统状态');