# 前端 - Overview 模块（总览）

## 模块概述
系统首页，展示模型/Qdrant/Flask/设备四张状态卡片和记忆趋势图表。图表支持"累计曲线"和"新增曲线"两种视图切换，Flask 重启按钮可触发后端热重载。

## 文件位置
```
web/modules/overview/
├── overview.html   # HTML模板 + CSS（内联）
└── overview.js     # 页面逻辑
```

## 界面布局
```
┌──────────┬──────────┬──────────┬──────────┐
│ 模型状态  │ Qdrant   │ Flask    │ 设备信息  │  ← 四张状态卡片
│ badge OK  │ badge OK │ 重启按钮  │ CPU/RAM   │
└──────────┴──────────┴──────────┴──────────┘
┌──────────────────────────────────────────────┐
│ 记忆数据  [累计● 新增●] [24h][7d][30d][全部]   │  ← 数据视图Tab + 图表Tab
│ ┌──────────────────────────────────────────┐  │
│ │  ECharts折线图（累计=紫色 / 新增=绿色）    │  │  ← 图表主体
│ └──────────────────────────────────────────┘  │
│  记忆总数: 1234              24h新增: 56       │  ← 统计数字（带递增动画）
└──────────────────────────────────────────────┘
```

## 交互逻辑流

### 页面加载（onPageLoad）
```
onPageLoad()
  ├── fetchAndDrawChart(_currentChartRange)   ← 立即加载图表（默认today视图）
  ├── fetchMemoryCount()                      ← 立即加载记忆总数（带递增动画）
  ├── loadOverviewPage()                      ← 并行请求 settings/status/system-info
  │     ├── 更新 Flask 卡片（端口/PID/运行时长/热重载开关）
  │     ├── 更新模型卡片（名称 badge）
  │     ├── 更新 Qdrant 卡片（host:port、collection、存储、维度等）
  │     └── 更新设备卡片（CPU%/温度、内存、GPU名称/显存/温度）
  ├── 启动模型轮询（2秒间隔，model_loaded && qdrant_ready 后停止）
  ├── 启动 Qdrant 轮询（2秒间隔，qdrant_ready 后停止）
  ├── 启动系统信息轮询（1秒间隔，持续更新）
  └── 绑定图表Tab点击事件
```

### Flask 重启流程
```
restartFlask()
  → confirm() 二次确认
  → btn.textContent = '重启中...'
  → POST /flask/restart
      → 后端写 backend/.restart_flask 标志文件
  → startFlaskPoll(true, onBack)
      轮询 GET /status，等待旧Flask死去：
      → 请求失败 → hasFailed=true，badge显示"重启Xs"
      → 请求成功 && hasFailed → 触发 onBack:
          onBack()
            → btn 恢复可用
            → _refreshAllCards(st)        ← 更新四张卡片
            → 销毁旧图表实例
            → fetchAndDrawChart()          ← 重画图表
            → fetchMemoryCount()            ← 刷新记忆数
            → startModelPoll()             ← 重启模型轮询
            → startQdrantPoll()            ← 重启Qdrant轮询
```

### 图表数据视图切换
```
点击 [累计] → _currentDataView='cumulative'
  → 显示 chartView，隐藏 addedView
  → 图例切换为紫色"累计"
  → fetchAndDrawChart(_currentChartRange)

点击 [新增] → _currentDataView='added'
  → 显示 addedView，隐藏 chartView
  → 图例切换为绿色"新增"
  → fetchAddedChart(_currentChartRange)
```

### 图表时间范围切换
```
点击 [24h / 7d / 30d / 全部]
  → 切换 active 样式
  → 根据 _currentDataView 调用对应图表刷新
  → 累计视图：fetchAndDrawChart(range)
  → 新增视图：fetchAddedChart(range)
```

## 数据流

### 状态卡片数据（来自 GET /status）
| 卡片 | 字段 |
|------|------|
| 模型 | `model_loaded`, `embedding_model`, `model_size` |
| Qdrant | `qdrant_ready`, `qdrant_host`, `qdrant_port`, `qdrant_collection`, `qdrant_storage_path`, `qdrant_disk_size`, `qdrant_top_k`, `embedding_dim` |
| Flask | `flask_port`, `flask_pid`, `flask_uptime`, `flask_reload` |

### 系统信息（来自 GET /system-info）
| 字段 | 说明 |
|------|------|
| `platform` | 系统平台 |
| `cpu_percent` | CPU 使用率 |
| `cpu_temperature` | CPU 温度（可选） |
| `memory_total/used/percent` | 内存总量/已用/百分比 |
| `gpu.name/memory_total/memory_used/temperature` | GPU 信息（可选） |

### 图表数据（来自 GET /chart-data?range=xxx）
```
返回: { data: [{ date: "2026-04-30", added: 5, total: 123 }] }
累计曲线: y轴 = data[].total
新增曲线: y轴 = data[].added（minInterval:1 强制整数刻度）
```

### 记忆总数（来自 GET /memory-count）
```
返回: { count: 1234 }
```

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：加载图表+总数+页面数据，启动各轮询 |
| `cleanup()` | 清除所有定时器，销毁图表实例（`getDom()` 空保护） |
| `loadOverviewPage()` | 并行加载 settings/status/system-info，更新四张卡片 |
| `startModelPoll()` | 2秒轮询 /status，模型就绪后停止 |
| `startFlaskPoll(waitRestart, onBack)` | 1秒轮询等待 Flask 重启恢复 |
| `startQdrantPoll()` | 2秒轮询 /status，Qdrant 就绪后停止 |
| `restartFlask()` | 重启按钮：POST /flask/restart，触发 onBack 恢复UI |
| `_refreshAllCards(st)` | 用最新状态刷新所有卡片 |
| `fetchAndDrawChart(range)` | 获取累计曲线数据并渲染 |
| `fetchAddedChart()` | 获取新增曲线数据并渲染 |
| `drawEChart(data, range)` | ECharts 渲染累计曲线（紫色） |
| `drawAddedChart(data, range)` | ECharts 渲染新增曲线（绿色，minInterval:1） |
| `fetchMemoryCount()` | 获取记忆总数并播放递增动画 |
| `animateCount(el, target)` | 数字递增动画（50ms/step，分10步） |

## 全局状态
```javascript
var _modelTimer     = null;   // 模型轮询定时器（2秒）
var _qdrantTimer    = null;   // Qdrant轮询定时器（2秒）
var _flaskTimer     = null;   // Flask重启等待定时器（1秒）
var _sysInfoTimer   = null;   // 系统信息轮询（1秒）
var _resizeTimer    = null;   // 防抖resize定时器
var _currentChartRange = 'today';  // 当前图表时间范围
var _currentDataView   = 'cumulative';  // 当前数据视图
var _chartInstance     = null;  // 累计图表ECharts实例
var _addedChartInstance = null;  // 新增图表ECharts实例
var _chartData          = null;  // 累计图表原始数据（tooltip用）
var _addedChartData     = null;  // 新增图表原始数据
var _flaskRestarting    = false; // 重启中标志
```

## 重启后端交互链
```
前端点击[重启]
  → POST /flask/restart              (status.py:130)
      → 写 backend/.restart_flask 标志文件
  → 1秒轮询 GET /status               (status.py:22)
  → PM monitor() 检测到标志文件        (process_manager.py:277)
  → netstat 找端口 PID                 (process_manager.py:137)
  → taskkill 杀死旧 Flask             (process_manager.py:145)
  → socket.bind 等待端口释放           (process_manager.py:180)
  → Popen 启动新 Flask                (process_manager.py:95)
  → _wait_url /health 等待就绪        (process_manager.py:103)
  → 前端轮询成功 → onBack()           (overview.js:650)
```

## 相关模块
- **Settings 模块**: 模型/设备配置，保存触发模型重载
- **Memory 模块**: 记忆管理，存入/删除后刷新图表
- **Router 模块**: 全局状态栏状态点轮询（每3秒 GET /status）

---

*最后更新: 2026-05-01*
