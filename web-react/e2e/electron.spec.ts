/* Electron 桌面壳（TC-ELEC）
 *
 * 使用 Playwright _electron 启动器加载 electron/main.js。
 * 前提：Flask 已在 18980 就绪（waitForBackend 逻辑被绕过）。
 */
import { test, expect, _electron, type ElectronApplication, type Page } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname2 = path.dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = path.resolve(__dirname2, '..', '..')
const MAIN_JS = path.join(PROJECT_ROOT, 'electron', 'main.js')

async function launchElectron(): Promise<{ app: ElectronApplication; win: Page }> {
  const app = await _electron.launch({
    args: [MAIN_JS],
    env: { ...process.env, ELECTRON_ENABLE_LOGGING: '1' } as Record<string, string>,
  })
  const win = await app.firstWindow()
  await win.waitForLoadState('domcontentloaded')
  return { app, win }
}

test.describe('TC-ELEC Electron 桌面壳', () => {
  test('ELEC-01/02/03 窗口启动、SPA 渲染与窗口规格', async () => {
    const { app, win } = await launchElectron()
    try {
      // 加载 URL 为 18980（读 .port_config）
      expect(win.url()).toContain('127.0.0.1:18980')
      // SPA 渲染：9 个导航项
      await expect(win.locator('.nav-item')).toHaveCount(9, { timeout: 20000 })
      // 窗口标题与尺寸
      const title = await win.title()
      expect(title).toBe('AiBrain')
      const winObj = await app.evaluate(({ BrowserWindow }) => {
        const w = BrowserWindow.getAllWindows()[0]
        return { width: w.getSize()[0], height: w.getSize()[1] }
      })
      expect(winObj.width).toBe(1400)
      expect(winObj.height).toBe(900)
    } finally {
      await app.close()
    }
  })

  test('ELEC-04 preload 桥接暴露 electronAPI', async () => {
    const { app, win } = await launchElectron()
    try {
      const hasApi = await win.evaluate(() => {
        const api = (window as any).electronAPI
        return !!api && typeof api.openInBrowser === 'function' && api.isElectron === true
      })
      expect(hasApi).toBe(true)
    } finally {
      await app.close()
    }
  })

  test('ELEC-05 关窗退出应用', async () => {
    const { app, win } = await launchElectron()
    await expect(win.locator('.nav-item').first()).toBeVisible({ timeout: 20000 })
    await win.close()
    // 窗口关闭 → 应用退出
    await expect
      .poll(async () => {
        try {
          return app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)
        } catch {
          return 0
        }
      }, { timeout: 10000 })
      .toBeLessThanOrEqual(0)
    await app.close().catch(() => {})
  })

  test('ELEC-06 F5 刷新不退出应用', async () => {
    const { app, win } = await launchElectron()
    try {
      await expect(win.locator('.nav-item').first()).toBeVisible({ timeout: 20000 })
      await win.keyboard.press('F5')
      // 刷新后 SPA 重新挂载，应用仍在
      await expect(win.locator('.nav-item')).toHaveCount(9, { timeout: 20000 })
      const wins = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)
      expect(wins).toBe(1)
    } finally {
      await app.close()
    }
  })

  test('ELEC-08 后端就绪时正常加载页面内容', async () => {
    const { app, win } = await launchElectron()
    try {
      await expect(win.locator('.statusbar')).toBeVisible({ timeout: 20000 })
      await expect(win.locator('.nav-item.active')).toBeVisible()
    } finally {
      await app.close()
    }
  })
})
