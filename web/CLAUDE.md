# web/ — Vue 3 前端

## 技术栈
- **框架**: Vue 3 (Composition API + `<script setup>`)
- **状态管理**: Pinia 3 | **路由**: Vue Router 4 (createWebHistory)
- **构建**: Vite 6 + TypeScript 5.8 | **桌面壳**: PyWebView 6
- **可视化**: ECharts 6 / @antv/g6 5 / force-graph / three.js / 3d-force-graph

## 目录结构
```
web/src/
├── main.ts                 # 入口
├── App.vue                 # 根组件 (NavSidebar + router-view + StatusBar)
├── router/index.ts         # 6 条路由，全部懒加载，/ → /overview
├── stores/                 # Pinia 状态管理
│   ├── config.ts           # 配置状态
│   ├── status.ts           # 实时状态 (模型/Qdrant/Flask)
│   └── wiki.ts             # Wiki 知识库状态
├── composables/            # 组合式函数
│   ├── useApi.ts           # API 调用封装 (fetch + 错误处理)
│   ├── useEcharts.ts       # ECharts 图表封装
│   ├── usePolling.ts       # 轮询工具
│   ├── useToast.ts         # Toast 通知
│   ├── ConsoleEngine.ts    # 控制台引擎
│   └── useConsoleState.ts  # 控制台状态
├── components/             # 公共组件
│   ├── NavSidebar.vue      # 侧边导航栏
│   ├── StatusBar.vue       # 底部状态栏 (模型/Qdrant/Flask 实时)
│   └── ConsolePanel.vue    # 开发者控制台 (`~` 键切换)
└── views/                  # 页面视图 (每个独立文件夹)
    ├── OverviewView/       # /overview — 系统概览卡片
    ├── MemoryView/         # /memory — 记忆管理
    │   ├── GraphTab/       # 知识图谱 (g6/force-graph/3d)
    │   ├── EntityTab/      # 实体管理
    │   ├── OrganizeTab/    # 记忆整理
    │   ├── SearchTab/      # 记忆搜索
    │   ├── StoreTab/       # 记忆存储
    │   └── SettingsTab/    # 记忆设置
    ├── StreamView/         # /stream — 操作流
    ├── WikiView/           # /wiki — Wiki 知识库
    ├── LogsView/           # /logs — 后端日志
    └── SettingsView/       # /settings — 系统设置
```

## 路由表
| 路径 | 视图 | 功能 |
|------|------|------|
| `/` | → `/overview` | 默认重定向 |
| `/overview` | OverviewView | 系统概览 (模型/Qdrant/Flask/Device/Memory 卡片) |
| `/memory` | MemoryView | 记忆管理 (图谱/搜索/存储/整理/设置) |
| `/stream` | StreamView | 操作流 (store/delete/update/search) |
| `/wiki` | WikiView | 知识库管理 (搜索/文件列表/索引) |
| `/logs` | LogsView | 后端日志查看 |
| `/settings` | SettingsView | 系统设置 (模型/Mem0/Wiki) |

## 关键说明
- Vite 开发服务器代理 API 请求到 Flask 后端 (配 `vite.config.ts`)
- `useApi.ts` 封装了统一的 fetch 调用和错误处理
- 图谱可视化支持 2D (g6 / force-graph) 和 3D (three.js)
- 测试使用 Playwright E2E 测试
