---
name: skl-playwright-test
description: >
  使用 Playwright 为 AiBrain 项目编写和运行 E2E 测试。当用户想要：测试前端页面、验证UI交互、
  编写E2E测试用例、跑Playwright测试、对某个页面做自动化验证、截图验证页面状态、测试API与UI联动时，
  请务必使用此技能！即使用户只说"帮我测一下XX页面"或"验证XX功能"，也应触发此技能。
---

# AiBrain Playwright E2E 测试技能

本技能用于为 AiBrain 项目编写和运行 Playwright E2E 测试。

## 项目上下文

AiBrain 是一个本地知识库系统：
- **前端**: Vue 3 + Vite + TypeScript，CSS class 命名风格
- **后端**: Flask，端口从 `.port_config` 动态读取（当前 19398）
- **测试目录**: `web/e2e/*.spec.ts`
- **配置文件**: `web/playwright.config.ts`
- **Playwright 版本**: `@playwright/test` ^1.59.1

Flask 后端同时提供 API 和前端静态文件，测试直接访问 Flask 端口，无需单独启动 Vite dev server。

## 服务启动（测试前必须执行）

测试依赖后端服务运行。按以下步骤操作：

### 1. 检查服务状态

读取 `.port_config` 获取 Flask 端口（第一个逗号分隔的值），然后检查端口是否在监听：

```bash
# 读取端口
cat .port_config
# 检查端口
netstat -ano | grep 19398 | grep LISTENING
```

### 2. 如果服务未运行，启动后端

```bash
# 无 UI 模式启动（推荐，仅启动 Qdrant + Flask）
venv312/Scripts/python.exe backend/launcher/start.py --no-ui
```

`start.py --no-ui` 会自动：清理旧进程 → 检查依赖 → 启动 Qdrant → 启动 Flask。

### 3. 等待服务就绪

轮询 Flask 端口直到响应：

```bash
# 简单健康检查
curl -s http://127.0.0.1:$(cut -d',' -f1 .port_config)/status | head -c 1
```

等待最多 30 秒。如果超时仍未就绪，报告错误让用户排查。

## 编写测试

### 文件命名与位置

新测试文件放在 `web/e2e/<功能名>.spec.ts`。

### 代码结构模板

```typescript
import { test, expect } from '@playwright/test'

test.describe('功能名称', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/路由路径', { waitUntil: 'networkidle' })
  })

  test('测试用例描述', async ({ page }) => {
    // 断言
    await expect(page.locator('.some-element')).toBeVisible()
  })
})
```

### 选择器策略

本项目使用 **CSS class 选择器**，不使用 data-testid：

```typescript
// 页面导航
page.locator('.nav-tab:has-text("文本")')

// 按钮点击
page.locator('.btn-primary')
page.locator('.btn-accent')
page.locator('.btn-refresh')

// 表单输入
page.locator('.search-bar input')
page.locator('textarea')

// 内容区域
page.locator('.memory-list')
page.locator('.status-card')
page.locator('.stat-value')
page.locator('.stat-label')

// 精确匹配 placeholder
page.locator('input[placeholder="搜索相关记忆..."]')
```

### 常见断言模式

```typescript
// 可见性
await expect(locator).toBeVisible()

// 文本匹配
await expect(locator).toHaveText('精确文本')
await expect(locator).toContainText('部分文本')

// 数量
await expect(locator).toHaveCount(4)

// CSS class
await expect(locator).toHaveClass(/active/)

// 属性
await expect(locator).toHaveAttribute('placeholder', '预期值')
await expect(locator).toBeEnabled()

// 数值比较（先获取文本再解析）
const text = await locator.textContent()
expect(parseInt(text || '0', 10)).toBeGreaterThanOrEqual(0)
```

### 异步等待

Flask 后端需要时间处理请求，合理使用等待：

```typescript
// 等待固定时间（用于 API 轮询等场景）
await page.waitForTimeout(2000)

// 优先使用 expect 的 timeout
await expect(locator).toBeVisible({ timeout: 5000 })
```

### API 注入测试数据

对于需要测试数据的场景，直接调用后端 API：

```typescript
import { test, expect, type APIRequestContext } from '@playwright/test'

// 生成唯一 ID 避免冲突
function uid(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
}

// 读取动态端口
function getBaseUrl(): string {
  return `http://127.0.0.1:19398`
}

// 通过 MCP API 存储记忆
async function mcpStore(request: APIRequestContext, text: string, linkEntities: string[]) {
  const r = await request.post(`${getBaseUrl()}/memory/mcp/store`, {
    data: { text, link_entities: linkEntities },
  })
  return await r.json()
}

// 在测试中使用
test('测试用例', async ({ page, request }) => {
  const e1 = uid('测试实体')
  await mcpStore(request, `测试内容: ${e1}`, [e1])
  // 等待后端处理
  await page.waitForTimeout(2000)
  // 继续 UI 验证...
})
```

### 截图测试

```typescript
test.describe('截图', () => {
  test('页面截图', async ({ page }) => {
    await page.goto('/路由', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.screenshot({ path: 'e2e/test-output/截图名.png', fullPage: false })
  })
})
```

截图输出到 `web/e2e/test-output/` 目录。

### Tab 切换测试模式

```typescript
test('Tab切换', async ({ page }) => {
  await page.goto('/memory', { waitUntil: 'networkidle' })

  // 切到目标 Tab
  await page.locator('.nav-tab:has-text("目标Tab")').click()
  await expect(page.locator('.target-panel')).toBeVisible()

  // 验证之前的 Tab 内容消失
  // 切回验证
  await page.locator('.nav-tab:has-text("原Tab")').click()
  await expect(page.locator('.original-panel')).toBeVisible()
})
```

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
cd web && npx playwright test e2e/文件名.spec.ts -g "describe名称"
```

### 调试模式

```bash
# 有头模式（显示浏览器）
cd web && npx playwright test e2e/文件名.spec.ts --headed

# 调试模式（逐步执行）
cd web && npx playwright test e2e/文件名.spec.ts --debug

# 查看 trace
cd web && npx playwright test e2e/文件名.spec.ts --trace on
```

### 注意事项

- 项目配置 `fullyParallel: false`，测试串行执行
- 默认使用 chromium 和 chrome 两个 project
- 失败时自动截图（`screenshot: 'only-on-failure'`）
- trace 仅在重试时记录（`trace: 'on-first-retry'`）

## 工作流程

1. **确认测试目标** — 用户要测什么页面/功能
2. **阅读源码** — 找到对应 Vue 组件，了解 CSS class、交互逻辑、API 调用
3. **检查服务** — 确认后端在运行，否则启动
4. **编写测试** — 按上述模板和选择器策略编写
5. **运行验证** — 先跑单个文件确认通过
6. **报告结果** — 告知用户通过/失败情况
