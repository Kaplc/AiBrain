# 前端 - Logs 模块（日志查看）

## 模块概述
日志查看页面，从后端读取日志文件内容，支持点击复制单行，按级别高亮显示。无过滤、无自动刷新、无设置面板。

## 文件位置
```
web/modules/logs/
├── logs.html   # HTML模板 + CSS（内联）
└── logs.js     # 页面逻辑
```

## 界面布局
```
┌─────────────────────────────────────────────────────┐
│ 系统日志                                    [刷新]    │  ← header + 刷新按钮
├─────────────────────────────────────────────────────┤
│ app.log | 共 X 条，显示 Y 条                     │  ← 元信息行
├─────────────────────────────────────────────────────┤
│ [10:30:25] [INFO]    系统启动成功                │
│ [10:30:26] [WARNING] 内存使用率较高              │  ← 级别高亮
│ [10:30:27] [ERROR]   数据库连接失败              │  ← 可点击复制
└─────────────────────────────────────────────────────┘
```

## 交互逻辑流

### 页面加载（onPageLoad）
```
onPageLoad()
  ├── loadLog()                   ← 立即加载一次
  └── btnRefreshLog.onclick = loadLog  ← 绑定刷新按钮
```

### 加载日志（loadLog）
```
loadLog()
  → 显示 loading 遮罩
  → GET /wiki/log?lines=300
  → 解析每行，按级别高亮（ERROR红色 / WARNING黄色 / INFO绿色）
  → 渲染到 logWrap，滚动到底部
  → 失败则显示错误提示
```

### 复制日志行（copyLogLine）
```
点击日志行
  → 提取行文本
  → navigator.clipboard.writeText (降级: execCommand copy)
  → 显示 "已复制" toast
```

## 数据流

### API 接口
```
GET /wiki/log?lines=300
返回:
{
  "file": "flask.log",
  "total_relevant": 1500,
  "returned": 300,
  "lines": [
    "[2026-04-30 10:30:25] [INFO] [flask] Application started",
    "[2026-04-30 10:30:26] [WARNING] Memory usage high"
  ]
}
```

### 级别高亮规则
| 匹配条件 | CSS 类 |
|---------|--------|
| `[ERROR]` 或 `error/fail/Exception` | `log-level-error` |
| `[WARNING]` 或 `warn/timeout/降级` | `log-level-warn` |
| `[INFO]` 或日期路径格式 | `log-level-info` |

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口：加载日志 + 绑定刷新按钮 |
| `loadLog()` | GET /wiki/log，渲染日志列表，滚动到底部 |
| `copyLogLine(el)` | 点击复制单行文本 |

## 全局状态
无页面级状态，所有操作都是瞬态的。

## 相关模块
- **后端 wiki_mod**: 提供 `/wiki/log` 端点，读取 `backend/logs/` 下的日志文件

---

*最后更新: 2026-05-01*
