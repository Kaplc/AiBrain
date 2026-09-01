/* ELEC-07 dev 模式：ELECTRON_DEV=1 时加载 Vite dev server (127.0.0.1:3000) */
import { test, expect, _electron } from '@playwright/test'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname2 = path.dirname(fileURLToPath(import.meta.url))
const PROJECT_ROOT = path.resolve(__dirname2, '..', '..')
const MAIN_JS = path.join(PROJECT_ROOT, 'electron', 'main.js')

test('ELEC-07 dev 模式加载 Vite dev server', async () => {
  const app = await _electron.launch({
    args: [MAIN_JS],
    env: { ...process.env, ELECTRON_DEV: '1' } as Record<string, string>,
  })
  try {
    const win = await app.firstWindow()
    await win.waitForLoadState('domcontentloaded')
    expect(win.url()).toContain('127.0.0.1:3000')
    await expect(win.locator('.nav-item')).toHaveCount(9, { timeout: 30000 })
    // dev server 下 React 热更新模块可用
    const title = await win.title()
    expect(title).toBe('AiBrain')
  } finally {
    await app.close()
  }
})
