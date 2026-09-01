/* Electron preload - 安全桥接层
 *
 * 暴露 window.electronAPI.openInBrowser() 供渲染进程调用，
 * 替代原 pywebview 的 window.pywebview.api.open_in_browser()
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  openInBrowser: () => ipcRenderer.invoke('open-in-browser'),
  isElectron: true,
})
