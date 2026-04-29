# 前端 - Overview 模块

## 模块概述
Overview（总览）模块是AiBrain的主仪表板页面，提供系统状态监控、记忆统计和性能图表等功能。

## 文件位置
```
web/modules/overview/
├── overview.html      # HTML模板
├── overview.js        # 主逻辑
└── overview.css       # 样式文件
```

## 功能特性

### 1. 系统状态监控
- **模型状态**: 显示BGE-M3模型加载状态
- **Qdrant状态**: 显示向量数据库连接状态
- **设备信息**: 显示CPU/GPU使用情况
- **实时更新**: 1秒轮询，双就绪后停止

### 2. 统计信息展示
- **记忆总数**: 当前记忆库中的总记录数
- **今日新增**: 当天新增的记忆数量
- **存储大小**: Qdrant数据库占用空间
- **模型信息**: 模型名称、向量维度、参数量

### 3. 数据可视化
- **时间趋势图**: 支持今日/本周/本月视图
- **记忆增长趋势**: 新增和删除记录统计
- **交互式图表**: 可切换时间范围

## API接口调用

### 状态查询
```javascript
GET /status
```
返回系统状态信息，包括：
- `model_loaded`: 模型加载状态
- `qdrant_ready`: Qdrant就绪状态
- `device`: 运行设备 (CPU/GPU)
- `embedding_model`: 模型名称
- `embedding_dim`: 向量维度
- `qdrant_host/port`: 数据库连接信息

### 记忆数量
```javascript
GET /memory-count
```
返回当前记忆总数。

### 图表数据
```javascript
GET /chart-data?range=today/week/month
```
返回指定时间范围的统计图表数据。

### 系统信息
```javascript
GET /system-info
```
返回CPU、内存使用情况等系统信息。

## UI组件设计

### 状态卡片 (Status Card)
```html
<div class="status-card" id="scModelCard">
  <div class="sc-label-row">
    <div class="sc-label" id="scModelLabel">模型状态</div>
    <span class="sc-badge" id="scModelBadge"></span>
  </div>
  <div class="sc-value" id="scModelValue"></div>
  <div class="sc-sub" id="scModelSub"></div>
</div>
```

### 图表容器
```html
<div class="chart-container">
  <div class="chart-header">
    <div class="chart-title">记忆增长趋势</div>
    <div class="chart-range">
      <button class="range-btn active" data-range="today">今日</button>
      <button class="range-btn" data-range="week">本周</button>
      <button class="range-btn" data-range="month">本月</button>
    </div>
  </div>
  <div class="chart-body">
    <canvas id="memChart"></canvas>
  </div>
</div>
```

## JavaScript核心逻辑

### 状态轮询机制
```javascript
// 模型 & Qdrant 状态轮询（1秒，两者都就绪后停止）
if (_overviewTimer) clearInterval(_overviewTimer);
_overviewTimer = setInterval(async () => {
  const st = await fetch(API + '/status').then(r => r.json());
  
  // 更新状态显示
  updateStatusDisplay(st);
  
  // 两者都就绪才停止轮询
  if (st.qdrant_ready && st.model_loaded) {
    clearInterval(_overviewTimer);
    _overviewTimer = null;
  }
}, 1000);
```

### 图表绘制函数
```javascript
function fetchAndDrawChart(range) {
  fetch(`${API}/chart-data?range=${range}`)
    .then(r => r.json())
    .then(data => {
      drawChart(data);
      _currentChartRange = range;
    });
}
```

### 记忆数量更新
```javascript
function fetchMemoryCount() {
  fetch(`${API}/memory-count`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('totalMemories').textContent = data.count;
    });
}
```

## 样式设计要点

### 响应式布局
- 移动端适配：状态卡片垂直排列
- 桌面端：两列并排显示
- 图表容器：自适应宽度

### 状态指示器
- **绿色圆点**: 正常状态
- **红色圆点**: 错误状态
- **黄色圆点**: 加载中状态
- **灰色圆点**: 未连接状态

### 颜色主题
- 主色调: #3b82f6 (蓝色)
- 成功色: #10b981 (绿色)
- 警告色: #f59e0b (黄色)
- 错误色: #ef4444 (红色)

## 数据流说明

### 初始化流程
1. 页面加载 → 调用 `onPageLoad()`
2. 立即获取图表数据和记忆总数
3. 启动状态轮询（1秒间隔）
4. 加载系统信息

### 用户交互流程
1. 点击时间范围按钮 → 切换图表数据
2. 状态变化 → 自动更新显示
3. 页面刷新 → 重新初始化

### 错误处理
1. API调用失败 → 显示错误状态
2. 图表加载失败 → 显示备用信息
3. 轮询异常 → 自动重试

## 配置参数

### 环境变量
```javascript
// API基础路径（从全局配置读取）
const API = window.API_BASE || 'http://127.0.0.1:18765';
```

### 轮询配置
- 轮询间隔: 1000ms
- 最大轮询时间: 无限制（直到双就绪）
- 超时处理: 网络错误自动重试

### 图表配置
- 今日视图: 按小时统计
- 本周视图: 按天统计（7天）
- 本月视图: 按天统计（30天）

## 性能优化

### 防抖处理
```javascript
// 窗口大小变化时重新绘制图表
var _resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    if (window._chartInstance) {
      window._chartInstance.resize();
    }
  }, 250);
});
```

### 内存管理
- 定时器及时清理
- 图表实例销毁
- 事件监听器移除

### 请求优化
- 并行请求状态和图表数据
- 缓存频繁访问的数据
- 减少不必要的轮询

## 扩展性设计

### 添加新状态指示器
1. 在HTML中添加状态卡片
2. 在JavaScript中添加更新逻辑
3. 在CSS中定义样式

### 添加新图表类型
1. 扩展 `/chart-data` API
2. 添加新的图表渲染逻辑
3. 添加图表切换控件

### 国际化支持
1. 提取文本到语言文件
2. 添加语言切换功能
3. 动态更新界面文本

## 常见问题

### Q: 状态一直显示"加载中"
- 检查Flask服务是否正常运行
- 检查网络连接
- 查看浏览器控制台错误

### Q: 图表不显示数据
- 检查 `/chart-data` API是否返回数据
- 检查Chart.js库是否加载
- 检查浏览器控制台错误

### Q: 轮询停止过早
- 检查模型和Qdrant是否真正就绪
- 检查状态API返回的数据
- 考虑增加延迟或手动刷新

## 相关模块
- **Memory模块**: 记忆管理和搜索
- **Stats模块**: 详细统计信息
- **Settings模块**: 系统配置管理

---

*最后更新: 2026-04-29*