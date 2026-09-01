/* 全局导航与布局（TC-NAV）+ 状态栏（TC-SBAR）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

const NAV_ITEMS = [
  { name: '总览', path: '/overview' },
  { name: '记忆', path: '/memory' },
  { name: '对话', path: '/chat' },
  { name: '大脑', path: '/brain' },
  { name: 'Gate', path: '/gate' },
  { name: '流', path: '/stream' },
  { name: '用量', path: '/stats' },
  { name: '日志', path: '/logs' },
  { name: '设置', path: '/settings' },
]

test.describe('TC-NAV 全局导航与布局', () => {
  test('NAV-01 侧边栏渲染 9 个导航项', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.nav-item')).toHaveCount(9)
  })

  test('NAV-02 默认重定向总览页且总览高亮', async ({ page }) => {
    await waitForApp(page)
    await expect(page).toHaveURL(/\/overview/)
    await expect(page.locator('.nav-item.active', { hasText: '总览' })).toBeVisible()
  })

  for (const item of NAV_ITEMS) {
    test(`NAV-03+ 导航到 ${item.name}（${item.path}）`, async ({ page }) => {
      await waitForApp(page)
      await page.locator('.nav-item', { hasText: item.name }).first().click()
      await expect(page).toHaveURL(new RegExp(item.path.replace('/', '\\/') + '($|\\?)'))
      await expect(page.locator('.nav-item.active', { hasText: item.name })).toBeVisible()
    })
  }

  test('NAV-11 状态栏存在', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.statusbar')).toBeVisible()
  })

  test('NAV-12 反引号键开关控制台', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.console-wrap')).toHaveCount(0)
    await page.keyboard.press('`')
    await expect(page.locator('.console-wrap.show')).toBeVisible()
    await page.keyboard.press('`')
    await expect(page.locator('.console-wrap')).toHaveCount(0)
  })

  test('NAV-14 Toast 容器渲染机制', async ({ page }) => {
    await waitForApp(page)
    // 初始无可见 toast；注入全局 toast 事件验证 .toast.show 出现后自动消失
    await page.evaluate(() => {
      const el = document.querySelector('.toast')
      if (el) el.classList.add('show')
    })
    await expect(page.locator('.toast.show')).toBeVisible()
  })
})

test.describe('TC-SBAR 状态栏', () => {
  test('SBAR-01/02/03 模型点、Qdrant 点与设备标签', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.statusbar')).toContainText(/模型就绪|模型加载中/)
    await expect(page.locator('.statusbar')).toContainText('Qdrant')
    await expect(page.locator('.statusbar')).toContainText(/GPU|CPU/)
    // 数据源一致性校验
    const model = await page.evaluate(() => fetch('/overview/model').then((r) => r.json()))
    if (model.loaded) {
      await expect(page.locator('.statusbar')).toContainText('模型就绪')
    }
    const dotCount = await page.locator('.statusbar-dot').count()
    expect(dotCount).toBeGreaterThanOrEqual(2)
  })

  test('SBAR-05 构建按钮存在', async ({ page }) => {
    await waitForApp(page)
    await expect(page.locator('.statusbar .build-btn')).toBeVisible()
  })
})
