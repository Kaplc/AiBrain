/* 设置页（TC-SET）+ Wiki 页（TC-WIKI）*/
import { expect, test } from '@playwright/test'
import { waitForApp } from './helpers'

test.describe('TC-SET 设置页', () => {
  test('SET-01 Tab 结构与默认激活', async ({ page }) => {
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.locator('.page-title')).toHaveText('设置')
    await expect(page.locator('.settings-tab')).toHaveCount(3)
    await expect(page.locator('.settings-tab.active')).toHaveText('模型')
    await expect(page.locator('.settings-panel')).toHaveCount(1)
  })

  test('SET-02 模型 Tab：设备选项/GPU 信息/按钮', async ({ page }) => {
    await page.route('**/settings/api', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ device: 'cpu' }) }))
    await page.route('**/statusbar/api', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ model_loaded: true, qdrant_ready: true, device: 'cpu', embedding_model: 'bge-m3 (remote)', embedding_dim: 1024, cuda_available: false, gpu_hardware: false }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    const panel = page.locator('.settings-panel')
    await expect(panel.locator('.setting-label', { hasText: '嵌入模型' })).toBeVisible()
    await expect(panel.locator('.setting-desc', { hasText: 'bge-m3' })).toBeVisible()
    await expect(panel.locator('.device-option').nth(0)).toContainText('CPU')
    await expect(panel.locator('.device-option').nth(1)).toContainText('GPU (CUDA)')
    await expect(panel.locator('.gpu-info')).toBeVisible()
    // CPU 单选默认选中
    await expect(panel.locator('input[name="device"]').nth(0)).toBeChecked()
    // GPU 不可用提示
    await expect(panel.locator('.gpu-info')).toContainText('GPU 选项不可用')
    await expect(panel.locator('.btn-secondary', { hasText: '重置' })).toBeVisible()
    await expect(panel.locator('.btn-accent', { hasText: '保存' })).toBeVisible()
  })

  test('SET-02b 重置按钮恢复已保存设备', async ({ page }) => {
    await page.route('**/settings/api', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ device: 'cpu' }) }))
    await page.route('**/statusbar/api', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ model_loaded: true, device: 'cpu', embedding_model: 'bge-m3', embedding_dim: 1024, cuda_available: true, gpu_hardware: true, gpu_name: 'RTX 4090' }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    // 切到 GPU 再重置
    await page.locator('.device-option', { hasText: 'GPU (CUDA)' }).click()
    await expect(page.locator('input[name="device"]').nth(1)).toBeChecked()
    await page.locator('.btn-secondary', { hasText: '重置' }).click()
    await expect(page.locator('input[name="device"]').nth(0)).toBeChecked()
    await expect(page.locator('.toast.show')).toContainText('已重置')
  })

  test('SET-03 LLM Tab 表单渲染', async ({ page }) => {
    await page.route('**/settings/aibrain-config', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          llm: {
            fields: [
              { key: 'api_key', label: 'API Key', type: 'password', value: '', default: '', placeholder: 'sk-...' },
              { key: 'base_url', label: 'Base URL', type: 'text', value: 'https://api.test.com', default: 'https://api.test.com' },
              { key: 'model', label: '模型', type: 'select', options: ['deepseek-chat', 'deepseek-reasoner'], value: 'deepseek-chat', default: 'deepseek-chat' },
            ],
          },
        }),
      })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    await page.locator('.settings-tab', { hasText: 'LLM' }).click()
    const panel = page.locator('.settings-panel')
    await expect(panel.locator('.setting-label', { hasText: 'API Key' })).toBeVisible()
    await expect(panel.locator('input[type="password"]')).toBeVisible()
    await expect(panel.locator('input[type="text"]')).toHaveValue('https://api.test.com')
    await expect(panel.locator('select.setting-select')).toHaveValue('deepseek-chat')
    await expect(panel.locator('.btn-secondary', { hasText: '恢复默认' })).toBeVisible()
  })

  test('SET-04 统计 Tab 渲染', async ({ page }) => {
    await page.route('**/overview/db-status', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, stats: { memories: 42 } }) })
    )
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    await page.locator('.settings-tab', { hasText: '统计' }).click()
    await expect(page.locator('.setting-label', { hasText: '统计数据库状态' })).toBeVisible()
    await expect(page.locator('.setting-desc')).toContainText('正常')
    await expect(page.locator('.stats-pre')).toContainText('memories')
  })

  test('SET-05 Tab 切换旧面板消失新面板渲染', async ({ page }) => {
    await page.route('**/settings/api', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ device: 'cpu' }) }))
    await page.route('**/statusbar/api', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ model_loaded: true, device: 'cpu', cuda_available: false, gpu_hardware: false }) }))
    await page.route('**/settings/aibrain-config', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ llm: { fields: [] } }) }))
    await page.route('**/overview/db-status', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: false }) }))
    await waitForApp(page)
    await page.locator('.nav-item', { hasText: '设置' }).first().click()
    await expect(page.locator('.settings-panel')).toHaveCount(1)
    await page.locator('.settings-tab', { hasText: 'LLM' }).click()
    await expect(page.locator('.settings-tab.active')).toHaveText('LLM')
    await page.locator('.settings-tab', { hasText: '统计' }).click()
    await expect(page.locator('.settings-tab.active')).toHaveText('统计')
    await page.locator('.settings-tab', { hasText: '模型' }).click()
    await expect(page.locator('.settings-tab.active')).toHaveText('模型')
    await expect(page.locator('.settings-panel')).toHaveCount(1)
  })
})

test.describe('TC-WIKI Wiki 页', () => {
  test('WIKI-01/02 页面标题与文件表格排序', async ({ page }) => {
    await page.route('**/wiki/list', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ files: [{ name: 'b.md', size: 20, chunks: 2 }, { name: 'a.md', size: 10, chunks: 1 }] }),
      })
    )
    await page.route('**/wiki/index', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ total_files: 2, total_chunks: 3, indexed: true }) })
    )
    await page.route('**/wiki/settings', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ wiki_dir: 'D:/wiki' }) }))
    await waitForApp(page)
    await page.goto('/wiki')
    await expect(page.locator('.page-title')).toHaveText('Wiki 知识库')
    await expect(page.locator('.wiki-table')).toBeVisible()
    // 默认文件顺序
    await expect(page.locator('.wiki-table tbody tr').nth(0)).toContainText('b.md')
    // 点击"文件名"表头排序 → a.md 升到第一
    await page.locator('.wiki-table thead th', { hasText: '文件名' }).click()
    await expect(page.locator('.wiki-table tbody tr').nth(0)).toContainText('a.md')
  })

  test('WIKI-03 侧栏三 Tab 切换', async ({ page }) => {
    await page.route('**/wiki/list', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ files: [] }) }))
    await page.route('**/wiki/index', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ total_files: 5, total_chunks: 12, indexed: false }) })
    )
    await page.route('**/wiki/settings', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) }))
    await waitForApp(page)
    await page.goto('/wiki')
    await expect(page.locator('.ws-tab')).toHaveCount(3)
    await expect(page.locator('.ws-tab.active')).toHaveText('统计')
    await expect(page.locator('.setting-label', { hasText: '文件数' })).toBeVisible()
    await expect(page.locator('.setting-desc').nth(0)).toHaveText('5')
    await page.locator('.ws-tab', { hasText: '操作' }).click()
    await expect(page.locator('.btn-search', { hasText: '刷新统计' })).toBeVisible()
    await page.locator('.ws-tab', { hasText: '设置' }).click()
    await expect(page.locator('.setting-label', { hasText: 'Wiki 目录' })).toBeVisible()
    // 切回统计状态保留
    await page.locator('.ws-tab', { hasText: '统计' }).click()
    await expect(page.locator('.setting-desc').nth(0)).toHaveText('5')
  })

  test('WIKI-04 设置表单可编辑', async ({ page }) => {
    await page.route('**/wiki/list', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ files: [] }) }))
    await page.route('**/wiki/index', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) }))
    await page.route('**/wiki/settings', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ wiki_dir: 'D:/wiki' }) }))
    await waitForApp(page)
    await page.goto('/wiki')
    await page.locator('.ws-tab', { hasText: '设置' }).click()
    const input = page.locator('.ws-panel .form-input')
    await expect(input).toHaveValue('D:/wiki')
    await input.fill('E:/new-wiki')
    await expect(input).toHaveValue('E:/new-wiki')
  })

  test('WIKI-05 搜索接口连通并渲染结果', async ({ page }) => {
    await page.route('**/wiki/list', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ files: [] }) }))
    await page.route('**/wiki/index', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) }))
    await page.route('**/wiki/settings', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({}) }))
    await page.route('**/wiki/search', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ results: [{ text: 'wiki 搜索结果内容' }] }) })
    )
    await waitForApp(page)
    await page.goto('/wiki')
    await page.locator('.wiki-search-bar .form-input').fill('测试')
    await page.locator('.btn-search', { hasText: '搜索' }).first().click()
    await expect(page.locator('.wiki-search-results')).toBeVisible()
    await expect(page.locator('.wsr-header')).toContainText('搜索结果 (1)')
    await expect(page.locator('.wsr-item')).toHaveText('wiki 搜索结果内容')
  })
})
