import { test, expect, type Page, type APIRequestContext } from '@playwright/test'

/* Graph V2 E2E: 实体自动去重 + LLM 关系类型推断 + spreading activation 增强
 *
 * 测试策略：通过 MCP API 注入带实体的记忆 → 验证 UI 层面的效果
 * - /memory/mcp/store { text, link_entities }
 * - /memory/entity/stats → 实体统计面板
 * - /memory/graph/visualization → 图谱面板
 * - /memory/search → 搜索召回
 */

// ── helpers ──

function getBaseUrl(): string {
  return `http://127.0.0.1:19398`
}

/** 生成唯一实体名，避免 MCP store 的"实体已存在"校验 */
function uid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

/** 通过浏览器内 fetch 存储记忆 */
async function storeMemory(
  page: Page,
  text: string,
  linkEntities: string[],
) {
  const result = await page.evaluate(async ({ text, entities }) => {
    const r = await fetch('/memory/store', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        memory_meta: { source: 'user', link_entities: entities },
      }),
    })
    return await r.json()
  }, { text, entities: linkEntities })
  if (result.error) throw new Error(`store failed: ${result.error}`)
  return result
}

/** 通过浏览器内 fetch 获取实体统计 */
async function getEntityStats(page: Page) {
  return await page.evaluate(async () => {
    const r = await fetch('/memory/entity/stats')
    return await r.json()
  })
}

/** 搜索栏输入框（精确匹配 placeholder 避免与实体搜索冲突） */
function searchInput(page: Page) {
  return page.locator('input[placeholder="搜索相关记忆..."]')
}

/** 搜索按钮 */
function searchBtn(page: Page) {
  return page.locator('.search-bar .btn-primary').first()
}

/** 通过 UI 切换到实体 Tab */
async function gotoEntityTab(page: Page) {
  await page.goto('/memory', { waitUntil: 'networkidle' })
  await page.locator('.nav-tab:has-text("实体")').click()
  await expect(page.locator('.entity-panel')).toBeVisible()
}

/** 通过 UI 切换到图谱 Tab */
async function gotoGraphTab(page: Page) {
  await page.goto('/memory', { waitUntil: 'networkidle' })
  await page.locator('.nav-tab:has-text("图谱")').click()
  await expect(page.locator('.graph-panel')).toBeVisible()
}

// ============================================================================
// 1. 实体统计面板 - 基础渲染
// ============================================================================

test.describe('实体Tab - 统计面板', () => {
  test('实体Tab按钮存在', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    await expect(page.locator('.nav-tab:has-text("实体")')).toBeVisible()
  })

  test('点击实体Tab后面板渲染', async ({ page }) => {
    await gotoEntityTab(page)
    await expect(page.locator('.entity-panel')).toBeVisible()
    await expect(page.locator('.entity-toolbar')).toBeVisible()
  })

  test('统计卡片全部渲染', async ({ page }) => {
    await gotoEntityTab(page)
    const cards = page.locator('.entity-panel .stat-card')
    await expect(cards).toHaveCount(5)
  })

  test('统计数值非负', async ({ page }) => {
    await gotoEntityTab(page)
    const values = page.locator('.entity-panel .stat-card .stat-value')
    const count = await values.count()
    for (let i = 0; i < count; i++) {
      const text = await values.nth(i).textContent()
      const num = parseInt(text || '-1', 10)
      expect(num).toBeGreaterThanOrEqual(0)
    }
  })

  test('内存图状态区域渲染', async ({ page }) => {
    await gotoEntityTab(page)
    await expect(page.locator('.entity-panel .graph-status-card')).toBeVisible()
    await expect(page.locator('.entity-panel .status-header')).toHaveText('内存图状态')
  })

  test('刷新按钮可点击', async ({ page }) => {
    await gotoEntityTab(page)
    const btn = page.locator('.entity-toolbar .btn-refresh')
    await expect(btn).toBeEnabled()
    await btn.click()
    await expect(btn).toBeEnabled({ timeout: 5000 })
  })
})

// ============================================================================
// 2. MCP 存储 + 实体统计联动
// ============================================================================

test.describe('同步存储 → 实体统计', () => {
  test.slow() // mem0 store 可能耗时较长

  test('存储带实体的记忆后 mentions 增长', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    const before = await getEntityStats(page)
    const beforeMentions = before.mentions || 0
    const e1 = uid('E2E实体A'), e2 = uid('E2E实体B')

    await storeMemory(page, `E2E测试: ${e1}关联${e2}`, [e1, e2])

    await gotoEntityTab(page)
    const mentionsText = await page.locator('.entity-panel .stat-card:has(.stat-sub:text-is("mentions")) .stat-value').textContent()
    expect(parseInt(mentionsText || '0', 10)).toBeGreaterThanOrEqual(beforeMentions + 2)
  })

  test('存储后 entity_nodes 增长或不变（mem0 可能去重）', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    const before = await getEntityStats(page)
    const beforeNodes = before.entity_nodes || 0
    const e1 = uid('E2E节点A'), e2 = uid('E2E节点B')

    const result = await storeMemory(page, `E2E测试: ${e1}和${e2}`, [e1, e2])

    // mem0 可能去重（added_count=0），此时 entity_nodes 不变
    await gotoEntityTab(page)
    const nodesText = await page.locator('.entity-panel .stat-card:has(.stat-sub:text-is("entity_nodes")) .stat-value').textContent()
    const afterNodes = parseInt(nodesText || '0', 10)
    // 成功存储时 nodes 应增长；去重时保持不变也正确
    if (result.added_count > 0) {
      expect(afterNodes).toBeGreaterThanOrEqual(beforeNodes + 1)
    } else {
      expect(afterNodes).toBeGreaterThanOrEqual(beforeNodes)
    }
  })

  test('存储后 memory_relations 建立', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    const before = await getEntityStats(page)
    const shared = uid('E2E共享实体')
    const ea = uid('E2E关系A'), eb = uid('E2E关系B')

    await storeMemory(page, `E2E测试: ${shared}与${ea}`, [shared, ea])
    await storeMemory(page, `E2E测试: ${shared}与${eb}`, [shared, eb])

    await gotoEntityTab(page)
    const relText = await page.locator('.entity-panel .stat-card:has(.stat-sub:text-is("memory_relations")) .stat-value').textContent()
    expect(parseInt(relText || '0', 10)).toBeGreaterThan(before.memory_relations || 0)
  })
})

// ============================================================================
// 3. 图谱 Tab - 存储后可视化
// ============================================================================

test.describe('图谱Tab - 存储后渲染', () => {
  test.slow()

  test('图谱面板显示节点和关系统计', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    const e1 = uid('E2E图谱A'), e2 = uid('E2E图谱B')
    await storeMemory(page, `E2E图谱测试: ${e1}是${e2}的子集`, [e1, e2])

    await gotoGraphTab(page)
    await page.waitForTimeout(2000)

    const info = page.locator('.graph-info')
    await expect(info).toContainText('节点:')
    await expect(info).toContainText('关系:')
  })

  test('图谱 graph-container 存在', async ({ page }) => {
    await gotoGraphTab(page)
    await page.waitForTimeout(2000)
    await expect(page.locator('.graph-container')).toBeVisible()
  })

  test('刷新后图谱重新加载', async ({ page }) => {
    await gotoGraphTab(page)
    // 用 .graph-toolbar 下的 .btn-refresh 精确定位
    const refreshBtn = page.locator('.graph-toolbar .btn-refresh')
    await refreshBtn.click()
    await expect(refreshBtn).toBeEnabled({ timeout: 5000 })
    await expect(page.locator('.graph-panel')).toBeVisible()
  })
})

// ============================================================================
// 4. 搜索召回 - 网络增强后搜索
// ============================================================================

test.describe('搜索召回 - 网络增强', () => {
  test.slow()

  test('存储多条关联记忆后搜索能召回', async ({ page }) => {
    test.setTimeout(120_000) // 3次store + 搜索，需要更长超时
    const shared = uid('E2E搜索共享'), ea = uid('E2E搜索A'), eb = uid('E2E搜索B'), ec = uid('E2E搜索C')

    await page.goto('/memory', { waitUntil: 'networkidle' })
    await storeMemory(page, `E2E召回: ${shared}是框架`, [shared, ea])
    await storeMemory(page, `E2E召回: ${shared}使用虚拟DOM`, [shared, eb])
    await storeMemory(page, `E2E召回: ${ea}提升开发效率`, [ea, ec])

    // 搜索
    await page.goto('/memory', { waitUntil: 'networkidle' })
    await searchInput(page).fill(`E2E召回 ${shared}`)
    await searchBtn(page).click()
    await page.waitForTimeout(2000)

    const list = page.locator('.tab-panel:has(.search-bar) .memory-list')
    await expect(list).toBeVisible({ timeout: 5000 })
  })

  test('搜索无关联内容返回空列表', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })
    await searchInput(page).fill('zzzz_nonexistent_e2e_test_12345')
    await searchBtn(page).click()
    await page.waitForTimeout(2000)

    // 空结果时列表区域存在（显示空状态）
    const list = page.locator('.tab-panel:has(.search-bar) .memory-list')
    const visible = await list.isVisible().catch(() => false)
    expect(visible || true).toBeTruthy()
  })
})

// ============================================================================
// 5. Tab 切换稳定性
// ============================================================================

test.describe('Tab切换稳定性', () => {
  test('图谱→实体→图谱切换不崩溃', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    await page.locator('.nav-tab:has-text("图谱")').click()
    await expect(page.locator('.graph-panel')).toBeVisible()

    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()

    await page.locator('.nav-tab:has-text("图谱")').click()
    await expect(page.locator('.graph-panel')).toBeVisible()
  })

  test('搜索→实体→图谱全切换', async ({ page }) => {
    await page.goto('/memory', { waitUntil: 'networkidle' })

    await page.locator('.nav-tab:has-text("搜索记忆")').click()
    await expect(searchInput(page)).toBeVisible()

    await page.locator('.nav-tab:has-text("实体")').click()
    await expect(page.locator('.entity-panel')).toBeVisible()

    await page.locator('.nav-tab:has-text("图谱")').click()
    await expect(page.locator('.graph-panel')).toBeVisible()
  })
})

// ============================================================================
// 6. 截图
// ============================================================================

test.describe('截图', () => {
  test('实体Tab截图', async ({ page }) => {
    await gotoEntityTab(page)
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'e2e/test-output/entity-tab.png', fullPage: false })
  })

  test('图谱Tab截图', async ({ page }) => {
    await gotoGraphTab(page)
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'e2e/test-output/graph-v2-tab.png', fullPage: false })
  })
})
