/* ==================== 命令入口 ==================== */
// 自动扫描并加载console目录下所有cmd_*.js文件
// 流程：从后端API获取命令文件列表 → 动态加载每个文件 → registerCommand注册命令

async function loadAllCommands() {
  try {
    // 从后端API获取命令文件列表
    const resp = await fetch(API + '/console/commands');
    const data = await resp.json();
    const commands = data.commands || [];

    if (commands.length === 0) {
      console.log('[console] no commands found');
      return;
    }

    // 动态加载每个命令文件
    commands.forEach(file => {
      const script = document.createElement('script');
      script.src = 'console/' + file;
      script.onload = () => console.log(`[console] loaded: ${file}`);
      script.onerror = (e) => console.warn(`[console] failed to load: ${file}`);
      document.body.appendChild(script);
    });

    console.log(`[console] loaded ${commands.length} command files`);
  } catch (e) {
    console.error('[console] failed to load commands:', e);
  }
}

// 页面加载时自动扫描并加载
loadAllCommands();