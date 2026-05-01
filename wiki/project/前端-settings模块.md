# 前端 - Settings 模块（设置）

## 模块概述
全局设置页，三个Tab：模型（推理设备切换）、mem0.json（动态表单）、wiki.json（动态表单）。配置数据从后端schema动态生成表单。

## 文件位置
```
web/modules/settings/
├── settings.html   # HTML模板 + CSS（内联）
└── settings.js     # 页面逻辑
```

## 界面布局
```
┌──────────────────────────────────────────┐
│ 设置                                     │
│ [模型] [mem0.json] [wiki.json]           │  ← Tab切换
├──────────────────────────────────────────┤
│ 模型Tab:                                 │
│  模型: [BAAI/bge-m3 ▼]  bge-m3 · 1024维 │
│  推理设备: [自动 ▼]                       │
│  ✅ 检测到 GPU: NVIDIA ...               │
│  [重置] [保存]                           │
├──────────────────────────────────────────┤
│ mem0.json Tab / wiki.json Tab:           │
│  (动态表单，根据后端schema生成)            │
│  目录字段 → 带浏览按钮 + 存在性检查       │
│  [恢复默认] [保存]                       │
└──────────────────────────────────────────┘
```

## 交互逻辑流

### 页面加载
```
onPageLoad()
  └── loadSettingsPage()
        ├── 并行请求: GET /settings, GET /status, GET /aibrain-config
        ├── 更新模型Tab: 设备选择器、GPU检测信息
        ├── renderDynamicForms(aibrain)  ← 根据schema动态渲染mem0/wiki表单
        └── initDirChecks()             ← 给目录输入框绑定change/blur事件
```

### 模型Tab - 保存设备
```
选择设备(auto/gpu/cpu) → pendingDevice更新
点击[保存] → applySettings()
  → POST /reload-model { device: pendingDevice }
  → 成功: toast提示，savedDevice同步
  → 无变更: toast"设置未变更"
```

### 动态表单Tab - 保存配置
```
点击[保存] → saveMem0Config() / saveWikiConfig()
  → 遍历 aibrainConfig 对应 fields，收集表单值
  → 嵌套字段处理：如 key='llm_provider' → {"llm": {"provider": ...}}
  → POST /save-aibrain-config { mem0: {...} } 或 { wiki: {...} }
```

### GPU 硬件检测特殊状态
```
cuda_available=false + gpu_hardware=true
  → 显示警告提示：检测到 NVIDIA GPU，但安装的是 CPU 版 PyTorch
  → 提供 pip 安装命令提示
```

### 目录浏览
```
点击[📁] → browseDir(inputId)
  → POST /select-directory (后端原生选择器)
  → 失败降级: 创建webkitdirectory的input元素
  → 选择后自动调用 checkDirExists(inputId)
```

### 目录存在性检查
```
输入框 change/blur → checkDirExists(inputId)
  → POST /check-path { path }
  → 存在: 显示 ✓ (绿色)
  → 不存在: 显示 ✗ 不存在 (红色)
```

## 数据流

### 配置加载
```
GET /settings          → { device: "cpu" }
GET /status            → { model_loaded, embedding_model, cuda_available, gpu_name, ... }
GET /aibrain-config    → { mem0: { fields: [...] }, wiki: { fields: [...] } }
```

### 动态表单schema格式
```json
{
  "mem0": {
    "fields": [
      { "key": "wiki_dir", "label": "Wiki目录", "type": "dir", "value": "wiki", "default": "wiki" },
      { "key": "chunk_size", "label": "分块大小", "type": "number", "value": 1200, "default": 1200 },
      { "key": "llm_provider", "label": "LLM Provider", "type": "text", "value": "", "default": "" }
    ]
  }
}
```

### 配置保存
```
POST /save-aibrain-config { mem0: { wiki_dir: "...", chunk_size: 1200, llm: { provider: "..." } } }
POST /reload-model { device: "gpu" }
POST /select-directory  → { path: "C:\\..." }
POST /check-path { path } → { exists: true }
```

### GPU 检测逻辑（根据 status 字段组合判断）
| cuda_available | gpu_hardware | 显示 |
|----------------|-------------|------|
| true | - | 绿色提示，GPU 可用 |
| false | true | 黄色警告，提示安装 GPU 版 PyTorch |
| false | false | 红色提示，未检测到 GPU |

## 核心函数
| 函数 | 说明 |
|------|------|
| `onPageLoad()` | 入口，调用 loadSettingsPage() |
| `loadSettingsPage()` | 并行加载配置，渲染表单 |
| `renderDynamicForms(config)` | 根据schema渲染mem0/wiki表单 |
| `renderFields(fields, prefix)` | 生成表单HTML（目录字段带浏览按钮） |
| `applySettings()` | 保存设备设置并重载模型 |
| `saveMem0Config()` | 收集mem0表单值并保存（含嵌套字段处理） |
| `saveWikiConfig()` | 收集wiki表单值并保存 |
| `browseDir(inputId)` | 调用后端目录选择器，降级使用原生input |
| `checkDirExists(inputId)` | POST /check-path 检查目录是否存在（change/blur触发） |
| `initDirChecks()` | 渲染后给所有目录字段绑定change/blur事件 |
| `switchTab(tab)` | 切换Tab |
| `selectDevice(val)` | 更新 pendingDevice 并同步UI |
| `resetSettings()` / `resetMem0Config()` / `resetWikiConfig()` | 恢复默认 |

## 全局状态
```javascript
var pendingDevice = 'cpu';    // 待保存的设备选择
var savedDevice = 'cpu';      // 已保存的设备
var aibrainConfig = null;     // 动态配置schema数据
```

---

*最后更新: 2026-05-01*
