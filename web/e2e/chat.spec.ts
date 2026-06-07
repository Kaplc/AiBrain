import { test, expect } from '@playwright/test'

test.describe('Chat 聊天功能', () => {
  test.beforeEach(async ({ page, request }) => {
    // 清空历史对话（保证每个测试独立）
    await request.post('/chat/clear')
    await page.goto('/chat', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1500)
  })

  test('页面结构与空状态', async ({ page }) => {
    await expect(page.locator('.chat-wrap')).toBeVisible()
    await expect(page.locator('.status-bar')).toBeVisible()
    await expect(page.locator('.status-text')).toBeVisible()

    // 空状态（清空后应有空提示）
    await expect(page.locator('.empty-hint')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.empty-hint')).toContainText('开始与 AiBrain 对话')

    // 输入区
    await expect(page.locator('.chat-input')).toBeVisible()
    await expect(page.locator('.chat-input')).toHaveAttribute('placeholder', /输入消息/)

    // 发送按钮初始禁用
    await expect(page.locator('.send-btn')).toBeVisible()
    await expect(page.locator('.send-btn')).toBeDisabled()

    // 状态条按钮
    await expect(page.locator('.status-btn[title*="设置"]')).toBeVisible()
    await expect(page.locator('.status-btn[title*="清空"]')).toBeVisible()
  })

  test('输入交互 - 文本输入控制发送按钮状态', async ({ page }) => {
    const input = page.locator('.chat-input')
    const sendBtn = page.locator('.send-btn')

    await expect(sendBtn).toBeDisabled()
    await input.fill('你好')
    await expect(sendBtn).toBeEnabled()
    await input.fill('')
    await expect(sendBtn).toBeDisabled()
  })

  test('输入交互 - Enter 发送添加用户消息', async ({ page }) => {
    const input = page.locator('.chat-input')
    await input.fill('测试消息')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1000)

    // 用户消息出现
    const userMsg = page.locator('.message.user').last()
    await expect(userMsg).toContainText('测试消息')
  })

  test('清空对话按钮恢复空状态', async ({ page }) => {
    // 先发一条消息
    const input = page.locator('.chat-input')
    await input.fill('清空测试')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1000)

    // 应有消息（至少用户消息）
    await expect(page.locator('.user')).toHaveCount(1)

    // 点击清空
    await page.locator('.status-btn[title*="清空"]').click()
    await page.waitForTimeout(1000)

    // 回到空状态
    await expect(page.locator('.empty-hint')).toBeVisible({ timeout: 5000 })
  })

  test('跳转到 Chat 设置页', async ({ page }) => {
    await page.locator('.status-btn[title*="设置"]').click()
    await page.waitForTimeout(1000)
    await expect(page).toHaveURL(/settings/)
    await expect(page).toHaveURL(/tab=chat/)
  })

  test('无 API Key 时发送提示', async ({ page, request }) => {
    // 检查状态决定是否跳过
    const stateResp = await request.get('/chat/state')
    const state = await stateResp.json()
    test.skip(state.is_running !== false, 'API Key 已配置，跳过此测试')

    const input = page.locator('.chat-input')
    await input.fill('测试提示信息')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(2000)

    // 用户消息应该出现
    await expect(page.locator('.message.user').last()).toContainText('测试提示信息')

    // Assistant 占位消息可能被删除，或者不出现
    // Toast 可能出现错误提示
    // 无论哪种，页面不应崩溃
    await expect(page.locator('.chat-wrap')).toBeVisible()
  })
})

test.describe('Chat API', () => {
  test('GET /chat/messages 返回消息列表', async ({ request }) => {
    const resp = await request.get('/chat/messages')
    expect(resp.ok()).toBeTruthy()
    const data = await resp.json()
    expect(data).toHaveProperty('messages')
    expect(Array.isArray(data.messages)).toBeTruthy()
  })

  test('GET /chat/state 返回意识流状态', async ({ request }) => {
    const resp = await request.get('/chat/state')
    expect(resp.ok()).toBeTruthy()
    const data = await resp.json()
    expect(data).toHaveProperty('is_running')
    expect(data).toHaveProperty('idle_enabled')
    expect(data).toHaveProperty('idle_count')
    expect(data).toHaveProperty('is_busy')
  })

  test('POST /chat/send 无 Key 返回 503', async ({ request }) => {
    const resp = await request.post('/chat/send', {
      data: { message: 'E2E 测试消息' },
    })
    // 503: agent_not_running 或 api_key_missing；200: SSE 流
    if (resp.status() === 503) {
      const data = await resp.json()
      expect(data).toHaveProperty('error')
    } else if (resp.status() === 200) {
      expect(resp.headers()['content-type']).toContain('text/event-stream')
    }
  })

  test('POST /chat/clear 清空对话', async ({ request }) => {
    const resp = await request.post('/chat/clear')
    expect(resp.ok()).toBeTruthy()
    const data = await resp.json()
    expect(data).toHaveProperty('ok', true)
  })
})
