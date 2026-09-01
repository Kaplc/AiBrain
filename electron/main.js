/* AiBrain Electron 主进程
 *
 * 职责：
 * - 读取项目根 .port_config 首端口作为 Flask 后端地址
 * - 创建 BrowserWindow 加载 http://127.0.0.1:<port>
 * - preload 暴露 openInBrowser 桥接（替代 pywebview api.open_in_browser）
 * - 窗口关闭 → 退出应用（与 process_manager「webview 退出 → 整体退出」语义对齐）
 * - 后端未就绪时显示等待提示，就绪后自动重载
 *
 * 环境变量：
 * - ELECTRON_DEV=1 时加载 http://127.0.0.1:3000（Vite dev server，代理后端）
 */
const { app, BrowserWindow, shell, ipcMain } = require('electron')
const path = require('path')
const http = require('http')
const fs = require('fs')

// 项目根目录 = electron/ 的上一级
const PROJECT_ROOT = path.resolve(__dirname, '..')
const PORT_CONFIG = path.join(PROJECT_ROOT, '.port_config')

function getApiPort() {
  try {
    const content = fs.readFileSync(PORT_CONFIG, 'utf-8').trim()
    const first = parseInt(content.split(',')[0], 10)
    if (!isNaN(first)) return first
  } catch {}
  return 18980
}

const API_PORT = getApiPort()
const isDev = process.env.ELECTRON_DEV === '1'
const loadUrl = isDev ? 'http://127.0.0.1:3000' : `http://127.0.0.1:${API_PORT}`

let mainWindow = null

function checkBackendReady() {
  return new Promise((resolve) => {
    const req = http.get(`${loadUrl}/overview/model`, { timeout: 2000 }, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function waitForBackend(maxRetries = 60) {
  for (let i = 0; i < maxRetries; i++) {
    if (await checkBackendReady()) return true
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'AiBrain',
    backgroundColor: '#0f1117',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  })

  // 窗口就绪后显示，避免白屏闪烁
  mainWindow.once('ready-to-show', () => mainWindow.show())

  // 外部链接用系统浏览器打开（等效原 open_in_browser 桥接）
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // 窗口关闭 → 退出应用（非 macOS）
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // 初始加载
  mainWindow.loadURL(loadUrl).catch(async () => {
    // 后端未就绪：等待后重载
    const ready = await waitForBackend()
    if (ready && mainWindow) {
      mainWindow.loadURL(loadUrl)
    }
  })

  // 页面加载失败（后端中途重启）自动重试
  mainWindow.webContents.on('did-fail-load', async (event, code, desc, url, isMainFrame) => {
    if (!isMainFrame || !mainWindow) return
    const ready = await waitForBackend(30)
    if (ready && mainWindow) mainWindow.loadURL(loadUrl)
  })
}

// openInBrowser IPC：在系统默认浏览器中打开当前 URL
ipcMain.handle('open-in-browser', async () => {
  if (mainWindow) {
    const url = mainWindow.webContents.getURL()
    if (url) await shell.openExternal(url)
  }
})

// 单实例锁
const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  app.whenReady().then(createWindow)

  app.on('window-all-closed', () => {
    // 与 process_manager 语义对齐：窗口关闭 → 整体退出
    app.quit()
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
}
