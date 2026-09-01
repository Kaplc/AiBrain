/* E2E 公共工具：等待前端应用就绪 + 常用断言助手 */
import { expect, type Page } from '@playwright/test'

/** 等待 React SPA 挂载完成（#root 渲染出侧边栏） */
export async function waitForApp(page: Page) {
  await page.goto('/')
  await expect(page.locator('.nav-item')).toHaveCount(9, { timeout: 20000 })
}

/** 点击侧边栏导航项（按名称）并等待路由跳转 */
export async function navTo(page: Page, name: string, path: string) {
  await page.locator('.nav-item', { hasText: name }).first().click()
  await expect(page).toHaveURL(new RegExp(path.replace('/', '\\/') + '($|\\?)'))
}

/** 等待某个 API 轮询完成（页面 console 无网络错误即可） */
export async function expectNoPageError(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(String(err)))
  return errors
}

/** 短轮询等待函数返回 true（用于异步状态检查） */
export async function pollUntil(fn: () => Promise<boolean>, timeoutMs = 10000, stepMs = 250) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await fn()) return true
    await new Promise((r) => setTimeout(r, stepMs))
  }
  return false
}
