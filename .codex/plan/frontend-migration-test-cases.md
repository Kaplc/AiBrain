# 前端迁移测试用例文档（Vue3 + PyWebView → Electron + React）

> 生成日期：2026-09-01
> 迁移范围：`web/`（Vue 3.5 + Vite + Pinia SPA，由 PyWebView 桌面壳承载）
> 迁移目标：`web-react/`（React 18 + TypeScript + Vite + zustand SPA）+ `electron/`（Electron 桌面壳）
> 后端不变：Flask :18980 托管 SPA 静态产物 + REST/SSE API
> 用例来源：现有 16 个 Playwright spec（174 个用例）+ 页面源码功能盘点

## 1. 测试环境与前置条件

| 项 | 值 |
|---|---|
| 后端 | Flask :18980（读取 `.port_config` 首端口），启动后需预热（日志出现 `Model loaded successfully on cpu`） |
| 前端构建 | `web-react/` 内 `npm run build` → 产物 `web-react/dist/`，Flask 启动时优先托管 |
| E2E（Web） | Playwright（chromium），baseURL = `http://127.0.0.1:18980` |
| E2E（Electron） | Playwright `_electron` 启动器，加载 Electron 主进程 |
| 浏览器参数 | 绕过代理、强制 WebGL（swiftshader），保证 3D 图谱可渲染 |

前置步骤：
1. `cd web-react && npm install && npm run build`
2. 启动后端：`python backend/app.py --flask-only`（或完整 `start.bat`）
3. 等待日志 `[INFO] Model loaded successfully on cpu`
4. `npx playwright test`（Web 用例）；`npx playwright test -c electron-playwright.config.ts`（Electron 用例）

## 2. 全局导航与布局（TC-NAV）

| ID | 用例 | 步骤 | 预期 |
|---|---|---|---|
| NAV-01 | 侧边栏渲染 9 个导航项 | 打开 `/` | `.nav-item` 数量 = 9（总览/记忆/对话/大脑/Gate/流/用量/日志/设置） |
| NAV-02 | 默认重定向总览页 | 打开 `/` | URL 变为 `/overview`，总览项高亮 |
| NAV-03~10 | 逐项导航（记忆/对话/大脑/Gate/流/用量/日志/设置） | 点击对应 `.nav-item` | URL 匹配对应路由，active 态迁移 |
| NAV-11 | 状态栏存在 | 打开任意页 | `.statusbar` 可见 |
| NAV-12 | 反引号键开关控制台 | 按 `` ` `` | `.console-wrap` 显示/隐藏 |
| NAV-13 | F5/Ctrl+R 刷新页面 | 按键 | 页面重载（Electron 中 reload 当前视图） |
| NAV-14 | Toast 容器存在 | 触发任一 toast | 右下角 `.toast.show` 出现后消失 |
| NAV-15 | 徽标点击在浏览器打开 | Electron 内点击 `.nav-logo` | 调用 `open_in_browser` 桥接（浏览器打开当前 URL）；浏览器环境 fallback `window.open` |

## 3. 状态栏（TC-SBAR）

| ID | 用例 | 预期 |
|---|---|---|
| SBAR-01 | 模型状态点 | `模型就绪`+绿点 或 `模型加载中`+黄点（数据源 `/overview/model.loaded`） |
| SBAR-02 | Qdrant 状态点 | ready → 绿点，否则红点（`/overview/qdrant.ready`） |
| SBAR-03 | 设备标签 | cuda → `GPU`，否则 `CPU` |
| SBAR-04 | 轮询周期 3s | 状态自动刷新 |
| SBAR-05 | 构建按钮触发构建 | 点击`构建` → POST `/overview/frontend/build` → 显示`构建中...` → 轮询 build_id → `构建成功`后自动 reload / `构建失败`红色提示 |

## 4. 总览页（TC-OV）

| ID | 用例 | 预期 |
|---|---|---|
| OV-01 | 状态卡片渲染 | 4 张 `.status-card`（模型/Qdrant/Flask/设备） |
| OV-02 | ModelCard | `.sc-label`=模型状态，badge ∈ {OK, ''} |
| OV-03 | QdrantCard | label=Qdrant 状态，badge ∈ {OK, ''} |
| OV-04 | FlaskCard | label=Flask 状态 + `.flask-restart-btn` 可见，badge ∈ {OK, restarting, err} |
| OV-05 | DeviceCard | label=设备信息，子项含 `CPU:` 与 `内存:` |
| OV-06 | 图表区域 | `.chart-section` 可见，`.chart-title`=记忆数据，canvas 存在 |
| OV-07 | 数据视图 Tab | 累计曲线默认激活；可切新增曲线并切回 |
| OV-08 | 时间范围 Tab | 近24小时默认；可切 7天/30天/全部；切`全部`时增量统计 `.stat-box:nth(1)` 隐藏，切回恢复 |
| OV-09 | 统计数值 | `记忆总数` label 存在且 value 非空（`/memory/count`） |
| OV-10 | Flask 重启交互 | 点击重启 → 按钮文本变`重启中...`（POST `/overview/flask/restart` 写标志文件） |
| OV-11 | 页面往返图表重绘 | 离开再回总览，图表区域仍可见 |
| OV-12 | 余额/Token 卡 | BalanceCard 显示账户余额（`/overview/balance`，未配 Key 显示提示）；TokenCard 显示 24h/7d/30d 用量（`/overview/token-usage`） |

## 5. 记忆页（TC-MEM，7 个 Tab）

| ID | 用例 | 预期 |
|---|---|---|
| MEM-00 | Tab 渲染与默认态 | 7 个 Tab（搜索/保存/合并/图谱/实体/图表/设置），默认`搜索记忆`激活；切 Tab 后旧 active 消失；记忆总数动画计数（`/memory/count`） |
| MEM-S1 | 搜索框/按钮/历史开关可见 | placeholder 正确、按钮文案、历史按钮存在 |
| MEM-S2 | 初始提示 | 未搜索时显示初始提示文案 |
| MEM-S3 | 输入触发搜索 | 点击按钮或 Enter → POST `/memory/search`，loading 期间输入与按钮禁用 |
| MEM-S4 | 空输入不触发 | 空串/纯空白不发起请求 |
| MEM-S5 | 结果卡片结构 | 卡片含分类标签、时间、相似度、短 ID；多条渲染多卡 |
| MEM-S6 | 空结果/无 score | 空结果显示空状态文案；API 无 score 时不显示分数 |
| MEM-S7 | 历史下拉 | 打开/外部点击关闭/清空按钮清列表/点击历史项回填并搜索（`/memory/search-history`） |
| MEM-S8 | 删除结果卡 | 卡片删除按钮 → POST `/memory/delete` 后卡片移除 |
| MEM-S9 | 搜索失败 | API 失败显示 error toast；新搜索替换旧结果 |
| MEM-ST1 | 保存 Tab | 切换/输入框可输入/保存按钮 → POST `/memory/store`，成功 toast、输入清空 |
| MEM-O1 | 合并(整理) Tab | 工具栏元素存在；阈值选择可选；开始分析按钮可点击；分析中显示暂停按钮，停止后恢复；空状态提示；分析后面板内容切换 |
| MEM-G1 | 图谱 Tab | Tab 点击后 GraphPanel 渲染；toolbar/统计/刷新按钮存在；canvas 渲染（3D force-graph）；刷新触发重新加载；切走再回正常 |
| MEM-E1 | 实体 Tab | 统计卡片全渲染且数值非负；内存图状态区渲染；刷新按钮可点击；带实体存储后 mentions/entity_nodes/memory_relations 增长或不变；图谱↔实体来回切换不崩溃 |
| MEM-C1 | 图表 Tab | ECharts 记忆趋势图渲染，切 Tab 重绘 |
| MEM-SET1 | 设置 Tab | 加载并显示记忆设置（`/memory` 设置接口），可修改保存 |
| MEM-TAB | 快速遍历全部 Tab 不崩溃；随机顺序切换后回到搜索记忆；刷新按钮点击后不切 Tab |

## 6. 对话页（TC-CHAT）

| ID | 用例 | 预期 |
|---|---|---|
| CHAT-01 | 页面结构与空状态 | 消息区/输入区/发送按钮（空输入禁用）渲染；无历史时显示空状态 |
| CHAT-02 | 输入控制发送按钮 | 有文本 → 可发送 |
| CHAT-03 | Enter 发送 | 追加用户消息，POST `/chat/send` |
| CHAT-04 | 回复打字机 | 后端写盘后经 SSE `/brain/events/stream` 或 seq 轮询刷新，新 assistant 消息逐字显示（约 1.5s），完成后补刷新 |
| CHAT-05 | 历史加载 | GET `/chat/history` 渲染持久化消息；`/chat/seq` 3s 轻量轮询，seq 变化才拉全量 |
| CHAT-06 | 意识流状态 | GET `/chat/state` 10s 轮询，展示 current_status/loop 状态 |
| CHAT-07 | 清空对话 | 按钮 → POST `/chat/clear` → 消息清空 → 空状态恢复 |
| CHAT-08 | 主动消息 | 触发按钮 → POST `/chat/proactive` → 刷新列表 |
| CHAT-09 | 无 API Key | POST `/chat/send` 返回 503 → error toast 提示配置 |
| CHAT-10 | 跳转设置 | 设置入口跳转 `/settings` |
| CHAT-API | API 契约 | `/chat/messages`、`/chat/state`、`/chat/send`(503)、`/chat/clear` 响应结构不变 |
| CHAT-KEEP | 状态保持 | 切走再回对话页，消息列表与轮询状态保持（等价 KeepAlive） |

## 7. 大脑页（TC-BRAIN，只读观测）

| ID | 用例 | 预期 |
|---|---|---|
| BRAIN-01 | 导航可达 | 侧边栏进入 Brain 页 |
| BRAIN-02 | 面板渲染 | 状态面板（BrainStatusPanel）+ run 列表可见（`/brain/state`、`/brain/runs/recent`） |
| BRAIN-03 | 只读请求 | 加载只发起 GET state/runs，不触发 life 控制接口 |
| BRAIN-04 | run 详情 | 点击 run 加载详情（无记录时跳过） |
| BRAIN-05 | 暂停自动刷新 | 暂停后停止轮询 state |
| BRAIN-06 | Gate 结果/待表达面板 | GateResultPanel、PendingExpressionPanel 数据渲染 |

## 8. Gate 页（TC-GATE）

| ID | 用例 | 预期 |
|---|---|---|
| GATE-01 | 列表渲染 | Gate 决策/待表达列表加载渲染 |
| GATE-02 | 审批操作 | 批准/拒绝操作调用对应 API 并刷新列表 |
| GATE-03 | 空状态 | 无待处理项显示空状态提示 |

## 9. 流页（TC-STREAM）

| ID | 用例 | 预期 |
|---|---|---|
| STREAM-01 | 标题与计数 | `MCP x 条 / 搜索 x 条 / 删除 x 条` 汇总文案 |
| STREAM-02 | 三列布局 | 保存/查询/删除三列流渲染（`/stream/api?action=store|search|delete&days=3`） |
| STREAM-03 | 轮询 | 2s 流刷新 + 1s pending 状态轮询 |
| STREAM-04 | 保存操作 | 输入文本 → POST `/memory/store` → toast`记忆已保存` → 流刷新出现新条目（新条目入场动画） |
| STREAM-05 | 搜索操作 | 输入 query → POST `/memory/search` → 结果浮层渲染 → 可关闭 |
| STREAM-06 | 删除操作 | 输入/点击条目 ID → POST `/memory/delete` → toast → 流刷新 |

## 10. 用量页（TC-STATS）

| ID | 用例 | 预期 |
|---|---|---|
| STATS-01 | 图表渲染 | Token 用量图表 canvas 渲染（`/chart-data`、`/overview/token-usage`） |
| STATS-02 | 数据切换 | 时间范围切换后图表刷新 |

## 11. 日志页（TC-LOGS）

| ID | 用例 | 预期 |
|---|---|---|
| LOGS-01 | 页面标题 | 标题渲染 |
| LOGS-02 | 输出区域 | `.log-output`（或等价）区域存在 |
| LOGS-03 | 刷新按钮 | 存在且点击后加载日志内容（`/logs/api`） |
| LOGS-04 | 自动滚动 | 日志默认滚动到底部 |

## 12. 设置页（TC-SET）

| ID | 用例 | 预期 |
|---|---|---|
| SET-01 | Tab 结构 | 3 个 Tab（模型/LLM/统计），默认模型 Tab 唯一激活 |
| SET-02 | 模型 Tab | 设备选项 CPU/GPU 可选；GPU 信息区域；重置/保存按钮存在 |
| SET-03 | LLM Tab | 表单渲染（api_key/base_url/model 等），保存与恢复默认按钮 |
| SET-04 | 统计 Tab | 统计信息渲染（stats.db 状态） |
| SET-05 | Tab 切换 | 切换后旧面板消失、新面板渲染，切回状态保留 |

## 13. Wiki 页（TC-WIKI，路由保留无侧边栏入口）

| ID | 用例 | 预期 |
|---|---|---|
| WIKI-01 | 页面标题 | 渲染 |
| WIKI-02 | 文件列表 | 表格渲染，表头可点击排序（`/wiki/list`） |
| WIKI-03 | 侧栏 Tab | 统计/操作/设置三个侧栏 Tab 可切换 |
| WIKI-04 | 设置表单 | 输入可编辑并可保存（`/wiki/settings`） |
| WIKI-05 | 搜索/索引 | 搜索（`/wiki/search`）、建索引（`/wiki/index`）与进度/日志接口连通 |

## 14. 后端 API 契约（TC-API，回归保障）

| ID | 端点 | 断言 |
|---|---|---|
| API-01 | GET `/overview/model` | 200，字段 loaded/device/embedding_model |
| API-02 | GET `/overview/qdrant` | 200，字段 ready/host/port/collection |
| API-03 | GET `/overview/flask` | 200，pid/port/uptime |
| API-04 | GET `/memory/count` | 200，count ≥ 0 |
| API-05 | GET `/chat/state`、`/chat/seq` | 200，字段结构不变 |
| API-06 | POST `/overview/frontend/build` → GET status | build_id 轮询至 done/failed |
| API-07 | GET `/brain/state`、`/brain/runs/recent` | 200 |
| API-08 | GET `/stream/api?action=store&days=3` | 200，items 数组 |

## 15. Electron 桌面壳（TC-ELEC，新增）

| ID | 用例 | 预期 |
|---|---|---|
| ELEC-01 | 窗口启动 | Electron 主进程启动，创建 BrowserWindow，加载 `http://127.0.0.1:18980`（读 `.port_config`） |
| ELEC-02 | 页面渲染 | 窗口内 SPA 正常渲染（`.nav-item` = 9） |
| ELEC-03 | 窗口规格 | 尺寸/标题与原 PyWebView 一致（1400x900，AiBrain） |
| ELEC-04 | open_in_browser 桥接 | preload 暴露 `window.electronAPI.openInBrowser()`，点击徽标调用 `shell.openExternal` |
| ELEC-05 | 关窗退出 | 窗口关闭 → app quit（非 darwin），与 process_manager `webview 退出 → 整体退出` 语义对齐 |
| ELEC-06 | F5 刷新 | 窗口内 reload 生效且不退出应用 |
| ELEC-07 | dev 模式 | `ELECTRON_DEV=1` 时加载 `http://127.0.0.1:3000`（Vite dev server，代理后端） |
| ELEC-08 | 后端未就绪 | 后端不可达时窗口显示等待提示，就绪后自动重载 |

## 16. 迁移一致性说明

- 选择器兼容：React 版保留 `.nav-item/.status-card/.sc-label/.statusbar/.console-wrap/.data-tab/.chart-tab/.stat-box/.flask-restart-btn` 等 class，最大化复用现有断言。
- 差异项：导航项现有代码为 9 项（旧 spec 写 8 项已过期，Wiki 已从侧边栏移除但路由保留）；本文档以现状为准。
- PyWebView 保留为可选回退（`--webview-only`），Electron 为新默认桌面壳；后端静态目录优先 `web-react/dist`，回退 `web/dist`。
