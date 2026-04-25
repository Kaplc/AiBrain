/* ==================== 控制台核心 ==================== */
// 核心引擎：日志输出、输入处理、历史记录、命令执行
// 其他命令文件通过 registerCommand() 注册

/* ==================== 命令注册表 ==================== */
var _cmdRegistry = {};
var _cmdHelps = [];

// 注册命令
// 参数：name命令名，handler处理函数，help帮助文本
// 流程：存入Registry → 添加到help列表
function registerCommand(name, handler, help) {
  _cmdRegistry[name] = handler;
  if (help) _cmdHelps.push(`  ${name} - ${help}`);
}

// 获取所有帮助文本
function getHelpTexts() {
  return _cmdHelps;
}

/* ==================== 控制台变量 ==================== */
var consoleHistory = [];
var historyIndex = -1;

/* ==================== 切换控制台显示 ==================== */
// 切换控制台显示/隐藏，显示时聚焦输入框
// 流程：classList.toggle('show') → 判断显示状态 → focus输入框/隐藏提示
function toggleConsole() {
  const el = document.getElementById('globalConsole');
  const hint = document.querySelector('.console-hint');
  el.classList.toggle('show');
  if (el.classList.contains('show')) {
    document.getElementById('consoleInput').focus();
    hint.classList.remove('show');
  }
}

/* ==================== 清空控制台 ==================== */
// 清空控制台输出区域的内容
function clearConsole() {
  document.getElementById('consoleOutput').innerHTML = '';
}

/* ==================== 输出日志到控制台 ==================== */
// 创建日志行元素，添加到输出区域，并自动滚动到底部
// 参数：message日志内容，level日志级别（info/warn/error/success/cmd）
// 流程：获取输出容器 → 获取当前时间 → 创建元素 → 添加类名和内容 → appendChild → scrollTop
function logToConsole(message, level = 'info') {
  const output = document.getElementById('consoleOutput');
  const time = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const line = document.createElement('div');
  line.className = `console-line con-line-${level}`;
  line.innerHTML = `<span class="con-time">${time}</span>${escHtml(message)}`;
  output.appendChild(line);
  output.scrollTop = output.scrollHeight;
}

/* ==================== 处理控制台输入 ==================== */
// 监听控制台输入框的按键事件，处理命令执行和历史翻阅
// 流程：Enter → 保存历史 → 清空输入 → executeCommand
//       ArrowUp → 历史上翻，ArrowDown → 历史下翻
function handleConsoleInput(e) {
  if (e.key === 'Enter') {
    const input = document.getElementById('consoleInput');
    const cmd = input.value.trim();
    if (!cmd) return;

    consoleHistory.unshift(cmd);
    if (consoleHistory.length > 50) consoleHistory.pop();
    historyIndex = -1;

    logToConsole(cmd, 'cmd');
    input.value = '';

    executeCommand(cmd);
  } else if (e.key === 'ArrowUp') {
    if (historyIndex < consoleHistory.length - 1) {
      historyIndex++;
      document.getElementById('consoleInput').value = consoleHistory[historyIndex];
    }
    e.preventDefault();
  } else if (e.key === 'ArrowDown') {
    if (historyIndex > 0) {
      historyIndex--;
      document.getElementById('consoleInput').value = consoleHistory[historyIndex];
    } else if (historyIndex === 0) {
      historyIndex = -1;
      document.getElementById('consoleInput').value = '';
    }
    e.preventDefault();
  }
}

/* ==================== 执行命令 ==================== */
// 解析并执行用户输入的命令
// 流程：解析命令 → 匹配注册的命令 → 执行对应操作 → 未找到则发送到后端
function executeCommand(cmd) {
  // 检查是否是内建命令
  if (cmd === 'clear' || cmd === 'cls') {
    clearConsole();
    return;
  }
  if (cmd === 'help') {
    logToConsole('可用命令：', 'info');
    _cmdHelps.forEach(h => logToConsole(h, 'info'));
    logToConsole('  help - 显示帮助', 'info');
    return;
  }

  // 从注册表查找命令
  const handler = _cmdRegistry[cmd];
  if (handler) {
    handler(cmd);
    return;
  }

  // 未找到，发送到后端执行
  fetch(API + '/console', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command: cmd})
  }).then(r => r.json())
    .then(d => {
      if (d.error) {
        logToConsole(d.error, 'error');
      } else if (d.result) {
        logToConsole(d.result, 'success');
      } else {
        logToConsole(JSON.stringify(d), 'info');
      }
    })
    .catch(e => {
      logToConsole(`执行失败: ${e.message}`, 'error');
    });
}

/* ==================== 拦截console输出 ==================== */
// 重写console方法，将所有日志输出到控制台面板
// 流程：保存原始console方法 → 创建捕获函数 → 替换console方法
// 作用：前端console.log/info/warn/error会自动显示在控制台
const _origLog = {log: console.log, info: console.info, warn: console.warn, error: console.error};
function _captureConsole(level) {
  return function(...args) {
    const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
    logToConsole(msg, level);
    _origLog[level].apply(console, args);
  };
}
console.log = _captureConsole('info');
console.info = _captureConsole('info');
console.warn = _captureConsole('warn');
console.error = _captureConsole('error');

/* ==================== 初始化控制台 ==================== */
// 绑定全局按键监听，显示快捷键提示
// 流程：keydown监听反引号键 → 切换控制台 → 显示3秒提示
function initConsole() {
  // 全局按键监听：按下~键切换控制台
  // 条件：不在输入框/文本域中，且按下反引号键
  document.addEventListener('keydown', e => {
    if (e.key === '`' && !e.ctrlKey && !e.altKey && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      toggleConsole();
      e.preventDefault();
    }
  });

  // 显示控制台快捷键提示（1秒后显示，3秒后淡出）
  setTimeout(() => {
    const hint = document.querySelector('.console-hint');
    if (hint) {
      hint.classList.add('show');
      setTimeout(() => hint.classList.remove('show'), 3000);
    }
  }, 1000);

  logToConsole('控制台已就绪，按 ~ 键打开', 'success');
}

// 页面加载时初始化
initConsole();

// 启动MCP命令队列轮询（每500ms检查一次）
setInterval(pollMcpCommands, 500);

// MCP命令队列轮询
// 流程：调用后端API获取命令队列 → 逐条执行 → 清空队列
async function pollMcpCommands() {
  try {
    const resp = await fetch(API + '/console/poll');
    const data = await resp.json();
    const commands = data.commands || [];

    if (commands.length === 0) return;

    // 逐条执行命令
    for (const cmd of commands) {
      if (cmd.action === 'log') {
        logToConsole(cmd.message, cmd.level || 'info');
      } else if (cmd.action === 'clear') {
        clearConsole();
      } else if (cmd.action === 'toggle') {
        toggleConsole();
      } else if (cmd.action === 'exec') {
        logToConsole(`> ${cmd.command}`, 'cmd');
        executeCommand(cmd.command);
      }
    }

    // 执行完成后清空队列
    await fetch(API + '/console/poll', {method: 'POST'});
  } catch (e) {
    // 静默失败，避免刷屏
  }
}