---
name: skl-playwright-test
description: >
  使用 Playwright 为 AiBrain 项目编写和运行 E2E 测试。当用户想要：测试前端页面、验证UI交互、
  编写E2E测试用例、跑Playwright测试、对某个页面做自动化验证、截图验证页面状态、测试API与UI联动时，测试一下XX功能等，都应该触发此技能。
  请务必使用此技能！即使用户只说"帮我测一下XX页面"或"验证XX功能"，也应触发此技能。
---

# AiBrain Playwright E2E 测试技能

## 项目上下文

AiBrain 是一个本地知识库系统：
- **前端**: Vue 3 + Vite + TypeScript，CSS class 命名风格（无 data-testid）
- **后端**: Flask，端口从 `.port_config` 动态读取（当前 19398）
- **测试目录**: `web/e2e/`，现有 **15 个 spec 文件**
- **配置文件**: `web/playwright.config.ts`
- **Playwright 版本**: `@playwright/test` ^1.59.1

Flask 后端同时提供 API 和前端静态文件，测试直接访问 Flask 端口，无需单独启动 Vite dev server。

## 现有测试文件

```
web/e2e/
├── navigation.spec.ts       # 全局导航、侧边栏、状态栏、控制台
├── overview.spec.ts         # Overview 页面卡片、图表、Tab切换、重启
├── chat.spec.ts             # Chat 页面：输入、发送、清空、状态 API
├── settings.spec.ts         # 设置页面
├── wiki.spec.ts             # Wiki 知识库
├── memory.spec.ts           # 记忆列表
├── memory-search.spec.ts    # 记忆搜索
├── organize.spec.ts         # 知识整理
├── steam.spec.ts            # 操作流
├── logs.spec.ts             # 日志查看
├── graph.spec.ts            # 知识图谱
├── graph-debug.spec.ts      # 图谱调试
├── graph-v2.spec.ts         # 图谱 v2
├── entity-rebuild.spec.ts   # 实体重建
└── tab-switch-stability.spec.ts  # Tab 切换稳定性
```

## 服务启动（测试前必须执行）

### 1. 读取端口

```bash
cat .port_config
# 输出示例: 19398,19399,19400,19401,19402
# 第一个值是 Flask 端口
```

### 2. 检查服务是否运行

```bash
netstat -ano | grep $(cut -d',' -f1 .port_config) | grep LISTENING
```

### 3. 启动后端（如果未运行）

```bash
# 无 UI 模式（推荐，仅启动 Qdrant + Flask，不打开浏览器）
venv312/Scripts/python.exe backend/launcher/start.py --no-ui
```

### 4. 等待服务就绪

后端启动后需要预热加载语义模型，观察日志直到出现初始化完成标记：

```bash
# 查看最新日志文件
tail -f logs/flask_*.log | grep -m1 "AiBrain 系统初始化完成"
```

出现 `[INFO] AiBrain 系统初始化完成` 表示后端就绪，可以开始测试。

## 编写测试

### 文件命名与位置

新测试文件放在 `web/e2e/<功能名>.spec.ts`。按功能模块划分，一个文件一个 describe 块。

### 基础模板

```typescript
import { test, expect } from '@playwright/test'

test.describe('功能名称', () => {
  test.beforeEach(async ({ page }) => {
    // 如果需要清理状态
    // await request.post('/api/clear')
    await page.goto('/路由路径', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000) // 等待前端渲染
  })

  test('测试用例描述', async ({ page }) => {
    await expect(page.locator('.some-element')).toBeVisible()
  })
})
```

### 选择器策略

本项目仅使用 **CSS class 选择器**，不 data-testid：

```typescript
// 页面导航
page.locator('.nav-item:has-text("记忆")')
page.locator('.nav-item.active .nav-label')

// 状态卡片（Overview 页面）
page.locator('.status-card')          // 所有卡片
page.locator('.status-card').nth(N)   // 第 N 个卡片
page.locator('.sc-label')             // 卡片标题
page.locator('[class*="badge"]')      // 状态徽章

// Token 图表（TokenCard）
page.locator('.chart-tab')            // 24h / 7d / 30d Tab
page.locator('.chart-tab.active')     // 当前激活的 Tab
page.locator('.chart-container')      // ECharts 图表容器
page.locator('.chart-stats .stat-box')// 统计数字
page.locator('.cache-bar-wrap')       // 缓存命中率
page.locator('.btn-refresh')          // 刷新按钮

// 余额卡片（BalanceCard）
page.locator('.balance-value')        // 余额数字
page.locator('.balance-detail span')  // 赠金/充值明细
page.locator('.today-cost')           // 今日消耗

// Chat 页面
page.locator('.chat-wrap')            // 聊天容器
page.locator('.chat-input')           // 输入框
page.locator('.send-btn')             // 发送按钮
page.locator('.message')              // 所有消息
page.locator('.message.user')         // 用户消息
page.locator('.message.assistant')    // 助手消息
page.locator('.empty-hint')           // 空状态提示
page.locator('.status-bar')           // 状态栏
page.locator('.status-btn')           // 状态栏按钮（清空/设置）
page.locator('.tool-calls')           // 工具调用显示区域
page.locator('.tool-call')            // 单个工具调用条目

// 按钮
page.locator('.btn-accent')
page.locator('.btn-primary')
page.locator('.flask-restart-btn')

// 表单
page.locator('.search-bar input')
page.locator('input[placeholder="搜索相关记忆..."]')
page.locator('textarea')

// 记忆页面
page.locator('.memory-list')
page.locator('.memory-item')
page.locator('.stat-value')
page.locator('.stat-label')

// 知识图谱
page.locator('.graph-canvas')
page.locator('.graph-controls')
page.locator('.graph-legend')

// 控制台（~ 快捷键唤出）
page.locator('.console-wrap')
page.locator('.btn-close')
```

### SSE 流式消息测试

Chat 页面使用 SSE（Server-Sent Events）流式输出。发送消息后需等待流式响应：

```typescript
test('发送消息后等待流式响应', async ({ page }) => {
  const input = page.locator('.chat-input')
  await input.fill('你好')
  await page.keyboard.press('Enter')

  // 用户消息立即出现
  await expect(page.locator('.message.user').last()).toContainText('你好')

  // 等待 assistant 消息出现（流式渲染可能需要时间）
  await expect(page.locator('.message.assistant').last()).toBeVisible({ timeout: 15000 })
})
```

### 工具调用测试

当 Chat 启用工具时（`tools_enabled=true`），发送消息后可能触发工具调用。前端流式事件 `type: tool_call` 会渲染 `.tool-calls` 区域：

```typescript
test('工具调用显示', async ({ page }) => {
  const input = page.locator('.chat-input')
  await input.fill('帮我查一下记忆')
  await page.keyboard.press('Enter')

  // 可能出现的工具调用信息
  const toolArea = page.locator('.tool-calls')
  if (await toolArea.isVisible({ timeout: 5000 }).catch(() => false)) {
    await expect(toolArea.locator('.tool-call')).toHaveCount(1)
  }
})
```

### 常见断言模式

```typescript
// 可见性
await expect(locator).toBeVisible()

// 精确文本匹配
await expect(locator).toHaveText('精确文本')

// 部分文本匹配
await expect(locator).toContainText('部分文本')

// 数量
await expect(locator).toHaveCount(4)

// CSS class 判断
await expect(locator).toHaveClass(/active/)

// 属性判断
await expect(locator).toHaveAttribute('placeholder', '预期值')
await expect(locator).toBeEnabled()
await expect(locator).toBeDisabled()

// 数值比较
const text = await locator.textContent()
const num = parseInt(text || '0', 10)
expect(num).toBeGreaterThanOrEqual(0)
```

### 异步等待

Flask 后端可能需要时间处理请求，合理使用等待：

```typescript
// 固定等待（用于 API 轮询、动态渲染等场景）
await page.waitForTimeout(2000)

// 优先使用 expect 的 timeout 参数
await expect(locator).toBeVisible({ timeout: 15000 })

// 等待网络请求完成
await page.waitForResponse(resp => resp.url().includes('/api/endpoint'))
```

### API 数据注入

需要测试数据时，直接调用后端 API：

```typescript
import { test, expect, type APIRequestContext } from '@playwright/test'

// 生成唯一 ID 避免冲突
function uid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

// 通过 MCP API 存储记忆
async function mcpStore(request: APIRequestContext, text: string, linkEntities: string[]) {
  const r = await request.post('/memory/mcp/store', {
    data: { text, link_entities: linkEntities },
  })
  return await r.json()
}

test('带测试数据的用例', async ({ page, request }) => {
  const e1 = uid('测试实体')
  await mcpStore(request, `测试内容: ${e1}`, [e1])
  await page.waitForTimeout(2000)  // 等待后端处理
  // 继续 UI 验证...
})
```

### 条件跳过

```typescript
test('需要特定条件', async ({ page, request }) => {
  const resp = await request.get('/chat/state')
  const state = await resp.json()
  test.skip(state.is_running !== false, '条件不满足，跳过')
  // 测试逻辑...
})
```

### 截图测试

```typescript
test('页面截图', async ({ page }) => {
  await page.goto('/路由', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  await page.screenshot({ path: 'e2e/test-output/截图名.png', fullPage: false })
})
```

截图输出到 `web/e2e/test-output/` 目录。

## 运行测试

### 运行全部测试

```bash
cd web && npx playwright test
```

### 运行指定文件

```bash
cd web && npx playwright test e2e/文件名.spec.ts
```

### 运行指定 describe 块

```bash
cd web && npx playwright test -g "describe名称"
```

### 调试模式

```bash
# 有头模式（显示浏览器窗口）
cd web && npx playwright test --headed

# 调试模式（逐步执行，暂停在每一步）
cd web && npx playwright test --debug

# 查看 trace 记录
cd web && npx playwright test --trace on
```

### 项目配置要点

- `fullyParallel: false` — 测试串行执行
- `retries: 0` — 失败不自动重试
- 默认使用 `chromium` 和 `chrome` 两个 project
- 失败时自动截图（`screenshot: 'only-on-failure'`）
- trace 在首次失败时记录（`trace: 'on-first-retry'`）

## 工作流程

1. **确认测试目标** — 用户要测什么页面/功能
2. **阅读源码** — 找到对应 Vue 组件，了解 CSS class、交互逻辑、SSE 事件类型
3. **检查服务** — 确认后端在运行，不在则启动
4. **参考现有测试** — 查看类似功能的 spec 文件，复用模式
5. **编写测试** — 按上述选择器和模板编写
6. **运行验证** — 单个文件运行确认通过
7. **报告结果** — 告知用户通过/失败/跳过情况
