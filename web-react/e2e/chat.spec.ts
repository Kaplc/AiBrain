/* 对话页（TC-CHAT）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

async function gotoChat(page: import('@playwright/test').Page) {
  await waitForApp(page)
  await page.locator('.nav-item', { hasText: '对话' }).first().click()
  await expect(page).toHaveURL(/\/chat/)
  await expect(page.locator('.chat-wrap')).toBeVisible()
}

test.describe('TC-CHAT 对话页', () => {
  test('CHAT-01 页面结构与空状态', async ({ page }) => {
    await gotoChat(page)
    await expect(page.locator('.messages')).toBeVisible()
    await expect(page.locator('.input-area .chat-input')).toBeVisible()
    await expect(page.locator('.send-btn')).toBeVisible()
    // 空输入禁用
    await expect(page.locator('.send-btn')).toBeDisabled()
    // 状态条渲染
    await expect(page.locator('.chat-wrap .status-bar')).toBeVisible()
  })

  test('CHAT-02 输入控制发送按钮', async ({ page }) => {
    await gotoChat(page)
    const input = page.locator('.chat-input')
    const send = page.locator('.send-btn')
    await input.fill('你好')
    await expect(send).toBeEnabled()
    await input.fill('')
    await expect(send).toBeDisabled()
  })

  test('CHAT-03 Enter 发送追加用户消息', async ({ page }) => {
    await gotoChat(page)
    const msg = 'E2E测试消息-' + Date.now()
    await page.locator('.chat-input').fill(msg)
    await page.locator('.send-btn').click()
    // 本地立即追加用户消息
    await expect(page.locator('.message.user .msg-content', { hasText: msg })).toBeVisible()
    // 输入框清空
    await expect(page.locator('.chat-input')).toHaveValue('')
  })

  test('CHAT-05 历史加载', async ({ page }) => {
    // 拦截历史接口返回持久化消息
    await page.route('**/chat/history', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            { role: 'user', content: '历史用户消息', created_at: '2026-09-01 10:00:00' },
            { role: 'assistant', content: '历史助手回复', created_at: '2026-09-01 10:00:05' },
          ],
        }),
      })
    )
    await page.route('**/chat/seq', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ seq: 2 }) }))
    await page.route('**/chat/state', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ life_loop_status: 'idle', current_activity: 'wait', idle_seconds: 10, energy: 0.8, scheduler_running: false, drives: {}, reflection: {} }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '对话' }).first().click()
    await expect(page.locator('.message.user .msg-content', { hasText: '历史用户消息' })).toBeVisible()
    await expect(page.locator('.message.assistant .msg-content', { hasText: '历史助手回复' })).toBeVisible()
  })

  test('CHAT-06 意识流状态展示', async ({ page }) => {
    await gotoChat(page)
    await expect(page.locator('.chat-wrap .status-bar .status-text')).toBeVisible()
  })

  test('CHAT-07 清空对话', async ({ page }) => {
    await gotoChat(page)
    await page.route('**/chat/clear', (route) => route.fulfill({ contentType: 'application/json', body: '{}' }))
    // 先本地添加一条消息再清空
    await page.locator('.chat-input').fill('临时消息')
    await page.locator('.chat-input').press('Enter')
    await page.locator('.status-btn[title="清空对话"]').click()
    await expect(page.locator('.empty-hint')).toBeVisible()
    await expect(page.locator('.toast.show')).toContainText('对话已清空')
  })

  test('CHAT-09 无 API Key 时 503 错误 toast', async ({ page }) => {
    await gotoChat(page)
    await page.route('**/chat/send', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: '请先配置 Chat API Key' }) })
    )
    await page.locator('.chat-input').fill('触发503')
    await page.locator('.chat-input').press('Enter')
    await expect(page.locator('.toast.error.show')).toContainText('请先配置 Chat API Key')
  })

  test('CHAT-10 跳转设置', async ({ page }) => {
    await gotoChat(page)
    await page.locator('.status-btn[title="系统提示词"]').click()
    await expect(page.locator('.modal-overlay')).toBeVisible()
    await expect(page.locator('.modal-title')).toHaveText('系统提示词')
    await page.locator('.modal-close').click()
    await expect(page.locator('.modal-overlay')).toHaveCount(0)
  })

  test('CHAT-KEEP 切走再回对话页消息保持', async ({ page }) => {
    await gotoChat(page)
    const msg = 'KEEP-' + Date.now()
    await page.locator('.chat-input').fill(msg)
    await page.locator('.chat-input').press('Enter')
    // 本地乐观追加或经 /chat/seq 轮询刷出，最长等 10s
    await expect(page.locator('.message .msg-content', { hasText: msg }).first()).toBeVisible({ timeout: 10000 })
    // 切到总览再切回（无 KeepAlive，重新挂载后经 /chat/history 加载持久化消息）
    await page.locator('.nav-item', { hasText: '总览' }).first().click()
    await page.locator('.nav-item', { hasText: '对话' }).first().click()
    await expect(page.locator('.message .msg-content', { hasText: msg }).first()).toBeVisible({ timeout: 10000 })
  })
})
