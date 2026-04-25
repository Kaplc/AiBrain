/* ==================== index 主脚本 ==================== */
// 页面加载完成后初始化路由和状态检查
// 流程：DOMContentLoaded → 调用initApp() → 初始化路由、状态检查、控制台

function initApp() {
  // 页面加载时默认打开 overview 页面
  loadPage('overview');

  // 启动状态检查轮询
  checkStatus();

  // 创建toast元素（如果不存在）
  if (!document.getElementById('toast')) {
    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }

  // 绑定F5刷新支持（PyWebView默认不支持）
  // 流程：keydown事件 → 检测F5或Ctrl+R → 阻止默认 → location.reload()
  document.addEventListener('keydown', (e) => {
    if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
      e.preventDefault();
      location.reload();
    }
  });
}

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', initApp);