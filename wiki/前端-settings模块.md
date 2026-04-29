# 前端 - Settings 模块

## 模块概述
Settings（设置）模块提供系统配置管理功能，包括设备选择、模型设置、界面偏好和系统信息查看，是AiBrain的配置控制中心。

## 文件位置
```
web/modules/settings/
├── settings.html      # HTML模板
├── settings.js        # 主逻辑
└── settings.css       # 样式文件
```

## 功能特性

### 1. 设备配置
- **设备选择**: CPU/GPU自动检测和手动选择
- **模型管理**: BGE-M3模型加载状态监控
- **性能监控**: 显示GPU内存使用情况
- **设备切换**: 运行时动态切换计算设备

### 2. 界面设置
- **主题选择**: 浅色/深色主题切换
- **语言设置**: 界面语言选择（中英文）
- **布局偏好**: 界面布局和字体大小调整
- **动画效果**: 启用/禁用界面动画

### 3. 系统信息
- **硬件信息**: CPU、内存、GPU详细信息
- **软件版本**: Python、PyTorch、Flask版本
- **存储状态**: 磁盘使用情况和剩余空间
- **网络信息**: 端口配置和连接状态

### 4. 高级设置
- **日志级别**: 调整系统日志详细程度
- **缓存管理**: 清理临时文件和缓存
- **端口配置**: 查看和修改服务端口
- **备份设置**: 数据备份和恢复配置

## 界面布局

### 设置分类布局
```html
<div class="settings-wrap">
  <!-- 设置导航 -->
  <div class="settings-nav">
    <div class="nav-group">
      <div class="nav-group-title">系统设置</div>
      <button class="nav-item active" data-section="device" onclick="switchSection('device')">
        <span class="nav-icon">⚙️</span>
        <span class="nav-text">设备设置</span>
      </button>
      <button class="nav-item" data-section="model" onclick="switchSection('model')">
        <span class="nav-icon">🧠</span>
        <span class="nav-text">模型设置</span>
      </button>
    </div>
    
    <div class="nav-group">
      <div class="nav-group-title">界面设置</div>
      <button class="nav-item" data-section="appearance" onclick="switchSection('appearance')">
        <span class="nav-icon">🎨</span>
        <span class="nav-text">外观</span>
      </button>
      <button class="nav-item" data-section="behavior" onclick="switchSection('behavior')">
        <span class="nav-icon">🔧</span>
        <span class="nav-text">行为</span>
      </button>
    </div>
    
    <div class="nav-group">
      <div class="nav-group-title">系统信息</div>
      <button class="nav-item" data-section="system" onclick="switchSection('system')">
        <span class="nav-icon">💻</span>
        <span class="nav-text">系统信息</span>
      </button>
      <button class="nav-item" data-section="storage" onclick="switchSection('storage')">
        <span class="nav-icon">💾</span>
        <span class="nav-text">存储</span>
      </button>
    </div>
  </div>

  <!-- 设置内容区域 -->
  <div class="settings-content">
    <div id="sectionDevice" class="settings-section active">
      <!-- 设备设置内容 -->
    </div>
    
    <div id="sectionModel" class="settings-section">
      <!-- 模型设置内容 -->
    </div>
    
    <!-- 其他部分... -->
  </div>
</div>
```

### 设备设置界面
```html
<div class="settings-card">
  <div class="card-header">
    <div class="card-title">计算设备</div>
    <div class="card-subtitle">选择模型推理使用的硬件设备</div>
  </div>
  
  <div class="card-body">
    <div class="setting-row">
      <div class="setting-label">当前设备</div>
      <div class="setting-control">
        <div class="device-selector">
          <label class="device-option">
            <input type="radio" name="device" value="cpu" checked>
            <div class="device-card">
              <div class="device-icon">💻</div>
              <div class="device-info">
                <div class="device-name">CPU</div>
                <div class="device-desc">稳定兼容，速度较慢</div>
              </div>
            </div>
          </label>
          
          <label class="device-option">
            <input type="radio" name="device" value="cuda">
            <div class="device-card">
              <div class="device-icon">🎮</div>
              <div class="device-info">
                <div class="device-name">GPU (CUDA)</div>
                <div class="device-desc">需要NVIDIA显卡，速度最快</div>
              </div>
            </div>
          </label>
        </div>
      </div>
    </div>
    
    <div class="setting-row">
      <div class="setting-label">GPU内存</div>
      <div class="setting-control">
        <div class="gpu-memory-info">
          <div class="memory-bar">
            <div class="memory-fill" style="width: 65%"></div>
          </div>
          <div class="memory-text">4.2GB / 8.0GB 已使用</div>
        </div>
      </div>
    </div>
  </div>
  
  <div class="card-footer">
    <button class="btn btn-primary" onclick="applyDeviceSettings()">应用设置</button>
    <div class="hint-text">切换设备需要重启模型加载</div>
  </div>
</div>
```

## API接口调用

### 获取当前设置
```javascript
GET /settings
```
返回当前系统设置：
- `device`: 当前设备设置 (cpu/cuda)
- `theme`: 界面主题 (light/dark)
- `language`: 界面语言
- `log_level`: 日志级别
- `auto_save`: 自动保存设置

### 更新设置
```javascript
POST /settings
{
  "device": "cuda",
  "theme": "dark",
  "language": "zh-CN"
}
```
更新系统设置，返回操作结果。

### 获取系统信息
```javascript
GET /system-info
```
返回系统硬件信息：
- `cpu_percent`: CPU使用率
- `memory_total`: 总内存（字节）
- `memory_used`: 已用内存（字节）
- `memory_percent`: 内存使用率
- `platform`: 操作系统信息
- `python_version`: Python版本

### 获取模型信息
```javascript
GET /model-info
```
返回模型相关信息：
- `model_name`: 模型名称
- `model_size`: 模型大小
- `embedding_dim`: 向量维度
- `device`: 当前加载设备
- `cuda_available`: CUDA是否可用

### 切换设备
```javascript
POST /switch-device
{
  "device": "cuda"
}
```
切换模型计算设备，返回切换结果。

### 清理缓存
```javascript
POST /clear-cache
```
清理系统缓存，返回清理结果。

## JavaScript核心逻辑

### 状态管理
```javascript
// 设置模块全局状态
var settingsState = {
  currentSection: 'device',
  settings: {},
  systemInfo: {},
  modelInfo: {},
  isLoading: false,
  isSaving: false,
  hasChanges: false
};

// 默认设置值
const defaultSettings = {
  device: 'cpu',
  theme: 'light',
  language: 'zh-CN',
  log_level: 'info',
  auto_save: true,
  animation: true,
  font_size: 'medium'
};
```

### 初始化加载
```javascript
function onPageLoad() {
  // 加载所有设置数据
  loadAllSettings();
  
  // 设置导航点击事件
  setupNavHandlers();
  
  // 设置表单变化监听
  setupFormListeners();
  
  // 初始化设备检测
  detectAvailableDevices();
  
  // 定期更新系统信息
  startSystemInfoPolling();
}

async function loadAllSettings() {
  settingsState.isLoading = true;
  
  try {
    // 并行加载所有数据
    const [settingsRes, systemRes, modelRes] = await Promise.all([
      fetchJson(`${API}/settings`),
      fetchJson(`${API}/system-info`),
      fetchJson(`${API}/model-info`)
    ]);
    
    settingsState.settings = { ...defaultSettings, ...settingsRes };
    settingsState.systemInfo = systemRes;
    settingsState.modelInfo = modelRes;
    
    // 渲染所有设置界面
    renderAllSections();
    
    // 应用当前主题
    applyTheme(settingsState.settings.theme);
    
  } catch (error) {
    console.error('加载设置失败:', error);
    showError('加载设置失败，使用默认设置');
    
    // 使用默认设置
    settingsState.settings = defaultSettings;
    renderAllSections();
  } finally {
    settingsState.isLoading = false;
  }
}
```

### 设备检测
```javascript
async function detectAvailableDevices() {
  try {
    const modelInfo = await fetchJson(`${API}/model-info`);
    
    // 更新设备选择器状态
    const cudaOption = document.querySelector('input[value="cuda"]');
    if (cudaOption) {
      cudaOption.disabled = !modelInfo.cuda_available;
      
      if (!modelInfo.cuda_available) {
        cudaOption.parentElement.classList.add('disabled');
        cudaOption.parentElement.title = 'CUDA不可用，请检查NVIDIA驱动';
      }
    }
    
    // 更新当前设备选择
    const currentDevice = modelInfo.device || 'cpu';
    document.querySelector(`input[value="${currentDevice}"]`).checked = true;
    
  } catch (error) {
    console.error('检测设备失败:', error);
  }
}
```

### 设置保存
```javascript
async function saveSettings() {
  if (settingsState.isSaving || !settingsState.hasChanges) {
    return;
  }
  
  settingsState.isSaving = true;
  
  try {
    // 收集所有设置值
    const settingsToSave = collectAllSettings();
    
    // 发送保存请求
    const response = await fetch(`${API}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settingsToSave)
    });
    
    const result = await response.json();
    
    if (result.ok) {
      // 更新本地状态
      settingsState.settings = settingsToSave;
      settingsState.hasChanges = false;
      
      // 应用设置变更
      applySettingsChanges(settingsToSave);
      
      // 显示成功消息
      showSuccess('设置已保存');
      
    } else {
      throw new Error(result.error || '保存失败');
    }
    
  } catch (error) {
    console.error('保存设置失败:', error);
    showError(`保存设置失败: ${error.message}`);
  } finally {
    settingsState.isSaving = false;
  }
}

function collectAllSettings() {
  return {
    device: getSelectedDevice(),
    theme: getSelectedTheme(),
    language: getSelectedLanguage(),
    log_level: getSelectedLogLevel(),
    auto_save: getAutoSaveSetting(),
    animation: getAnimationSetting(),
    font_size: getFontSizeSetting()
  };
}
```

### 设备切换
```javascript
async function switchDevice(device) {
  if (settingsState.isLoading) {
    showWarning('正在加载中，请稍候...');
    return;
  }
  
  const currentDevice = settingsState.modelInfo.device;
  if (device === currentDevice) {
    return; // 无需切换
  }
  
  const confirmed = confirm(`切换设备到 ${device.toUpperCase()}？模型需要重新加载`);
  if (!confirmed) return;
  
  try {
    showInfo('正在切换设备，请稍候...');
    
    const response = await fetch(`${API}/switch-device`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device })
    });
    
    const result = await response.json();
    
    if (result.ok) {
      showSuccess(`设备已切换到 ${device.toUpperCase()}`);
      
      // 重新加载模型信息
      const modelInfo = await fetchJson(`${API}/model-info`);
      settingsState.modelInfo = modelInfo;
      
      // 更新设备显示
      updateDeviceDisplay();
      
      // 重新检测设备
      detectAvailableDevices();
      
    } else {
      throw new Error(result.error || '切换失败');
    }
    
  } catch (error) {
    console.error('切换设备失败:', error);
    showError(`切换设备失败: ${error.message}`);
    
    // 恢复单选按钮状态
    document.querySelector(`input[value="${currentDevice}"]`).checked = true;
  }
}
```

## 数据渲染

### 设备设置渲染
```javascript
function renderDeviceSection() {
  const container = document.getElementById('sectionDevice');
  if (!container) return;
  
  const { modelInfo, systemInfo } = settingsState;
  const cudaAvailable = modelInfo.cuda_available || false;
  const currentDevice = modelInfo.device || 'cpu';
  
  // GPU内存信息
  let gpuMemoryHtml = '';
  if (cudaAvailable && systemInfo.gpu_memory) {
    const used = systemInfo.gpu_memory.used;
    const total = systemInfo.gpu_memory.total;
    const percent = total > 0 ? Math.round((used / total) * 100) : 0;
    
    gpuMemoryHtml = `
      <div class="setting-row">
        <div class="setting-label">GPU内存</div>
        <div class="setting-control">
          <div class="gpu-memory-info">
            <div class="memory-bar">
              <div class="memory-fill" style="width: ${percent}%"></div>
            </div>
            <div class="memory-text">
              ${formatBytes(used)} / ${formatBytes(total)} (${percent}%)
            </div>
          </div>
        </div>
      </div>
    `;
  }
  
  container.innerHTML = `
    <div class="settings-card">
      <div class="card-header">
        <div class="card-title">计算设备</div>
        <div class="card-subtitle">选择模型推理使用的硬件设备</div>
      </div>
      
      <div class="card-body">
        <div class="setting-row">
          <div class="setting-label">当前设备</div>
          <div class="setting-control">
            <div class="device-selector">
              <label class="device-option ${cudaAvailable ? '' : 'disabled'}">
                <input type="radio" name="device" value="cuda" 
                  ${currentDevice === 'cuda' ? 'checked' : ''}
                  ${cudaAvailable ? '' : 'disabled'}>
                <div class="device-card">
                  <div class="device-icon">🎮</div>
                  <div class="device-info">
                    <div class="device-name">GPU (CUDA)</div>
                    <div class="device-desc">
                      ${cudaAvailable ? '需要NVIDIA显卡，速度最快' : 'CUDA不可用'}
                    </div>
                  </div>
                  ${cudaAvailable ? '' : '<div class="device-badge disabled">不可用</div>'}
                </div>
              </label>
              
              <label class="device-option">
                <input type="radio" name="device" value="cpu" 
                  ${currentDevice === 'cpu' ? 'checked' : ''}>
                <div class="device-card">
                  <div class="device-icon">💻</div>
                  <div class="device-info">
                    <div class="device-name">CPU</div>
                    <div class="device-desc">稳定兼容，速度较慢</div>
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>
        
        ${gpuMemoryHtml}
        
        <div class="setting-row">
          <div class="setting-label">设备信息</div>
          <div class="setting-control">
            <div class="device-details">
              <div class="detail-item">
                <span class="detail-label">当前设备:</span>
                <span class="detail-value">${currentDevice.toUpperCase()}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">CUDA可用:</span>
                <span class="detail-value ${cudaAvailable ? 'yes' : 'no'}">
                  ${cudaAvailable ? '是' : '否'}
                </span>
              </div>
              ${modelInfo.gpu_name ? `
                <div class="detail-item">
                  <span class="detail-label">GPU型号:</span>
                  <span class="detail-value">${modelInfo.gpu_name}</span>
                </div>
              ` : ''}
            </div>
          </div>
        </div>
      </div>
      
      <div class="card-footer">
        <button class="btn btn-primary" onclick="applyDeviceSettings()" 
          ${currentDevice === getSelectedDevice() ? 'disabled' : ''}>
          应用设备设置
        </button>
        <div class="hint-text">切换设备需要重启模型加载</div>
      </div>
    </div>
  `;
}
```

### 系统信息渲染
```javascript
function renderSystemSection() {
  const container = document.getElementById('sectionSystem');
  if (!container) return;
  
  const { systemInfo } = settingsState;
  
  container.innerHTML = `
    <div class="settings-card">
      <div class="card-header">
        <div class="card-title">系统信息</div>
        <div class="card-subtitle">硬件和软件环境详情</div>
      </div>
      
      <div class="card-body">
        <div class="info-grid">
          <!-- CPU信息 -->
          <div class="info-card">
            <div class="info-icon">⚡</div>
            <div class="info-content">
              <div class="info-title">CPU</div>
              <div class="info-detail">${systemInfo.cpu_percent || 0}% 使用率</div>
              <div class="info-sub">${systemInfo.cpu_cores || '?'} 核心</div>
            </div>
          </div>
          
          <!-- 内存信息 -->
          <div class="info-card">
            <div class="info-icon">🧠</div>
            <div class="info-content">
              <div class="info-title">内存</div>
              <div class="info-detail">${systemInfo.memory_percent || 0}% 使用率</div>
              <div class="info-sub">${formatBytes(systemInfo.memory_used)} / ${formatBytes(systemInfo.memory_total)}</div>
            </div>
          </div>
          
          <!-- 操作系统 -->
          <div class="info-card">
            <div class="info-icon">💻</div>
            <div class="info-content">
              <div class="info-title">操作系统</div>
              <div class="info-detail">${systemInfo.platform || '未知'}</div>
              <div class="info-sub">${systemInfo.platform_version || ''}</div>
            </div>
          </div>
          
          <!-- Python版本 -->
          <div class="info-card">
            <div class="info-icon">🐍</div>
            <div class="info-content">
              <div class="info-title">Python</div>
              <div class="info-detail">${systemInfo.python_version || '未知'}</div>
              <div class="info-sub">${systemInfo.python_implementation || ''}</div>
            </div>
          </div>
        </div>
        
        <!-- 详细信息表格 -->
        <div class="info-table">
          <div class="table-header">
            <div class="table-cell">组件</div>
            <div class="table-cell">版本</div>
            <div class="table-cell">状态</div>
          </div>
          
          ${renderInfoTableRows()}
        </div>
      </div>
    </div>
  `;
}
```

## 工具函数

### 字节格式化
```javascript
function formatBytes(bytes) {
  if (bytes === 0 || bytes === undefined) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
```

### 主题应用
```javascript
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  
  // 保存到本地存储
  localStorage.setItem('aibrain-theme', theme);
  
  // 更新UI中的主题选择器
  const themeSelect = document.getElementById('themeSelect');
  if (themeSelect) {
    themeSelect.value = theme;
  }
}
```

### 设置变化检测
```javascript
function setupFormListeners() {
  // 监听所有表单变化
  document.addEventListener('change', (event) => {
    if (event.target.matches('input, select, textarea')) {
      settingsState.hasChanges = true;
      updateSaveButtonState();
    }
  });
  
  // 监听输入框实时变化
  document.addEventListener('input', (event) => {
    if (event.target.matches('input[type="text"], input[type="number"], textarea')) {
      settingsState.hasChanges = true;
      updateSaveButtonState();
    }
  });
}

function updateSaveButtonState() {
  const saveButton = document.getElementById('saveSettingsButton');
  if (saveButton) {
    saveButton.disabled = !settingsState.hasChanges;
    saveButton.textContent = settingsState.hasChanges ? '保存更改' : '已保存';
  }
}
```

## 样式设计要点

### 设置卡片设计
```css
.settings-card {
  background: white;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
  margin-bottom: 20px;
}

.card-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
}

.card-subtitle {
  font-size: 14px;
  color: #6b7280;
}

.card-body {
  padding: 24px;
}

.card-footer {
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
```

### 设置行布局
```css
.setting-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
}

.setting-label {
  width: 200px;
  padding-right: 20px;
  font-weight: 500;
  color: #374151;
}

.setting-control {
  flex: 1;
  min-width: 0;
}

.hint-text {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}
```

### 设备选择器
```css
.device-selector {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.device-option {
  cursor: pointer;
}

.device-option.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.device-option input[type="radio"] {
  display: none;
}

.device-card {
  width: 180px;
  padding: 16px;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-option input[type="radio"]:checked + .device-card {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.device-option:hover:not(.disabled) .device-card {
  border-color: #9ca3af;
}

.device-icon {
  font-size: 24px;
}

.device-info {
  flex: 1;
}

.device-name {
  font-weight: 500;
  margin-bottom: 2px;
}

.device-desc {
  font-size: 12px;
  color: #6b7280;
}

.device-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.device-badge.disabled {
  background-color: #f3f4f6;
  color: #6b7280;
}

.device-badge.recommended {
  background-color: #d1fae5;
  color: #065f46;
}
```

### 内存条样式
```css
.memory-bar {
  width: 200px;
  height: 8px;
  background-color: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.memory-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #3b82f6);
  transition: width 0.5s ease-out;
}

.memory-text {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}
```

## 性能优化

### 系统信息轮询
```javascript
let systemInfoTimer = null;

function startSystemInfoPolling() {
  if (systemInfoTimer) clearInterval(systemInfoTimer);
  
  // 每5秒更新一次系统信息
  systemInfoTimer = setInterval(() => {
    if (settingsState.currentSection === 'system') {
      updateSystemInfo();
    }
  }, 5000);
}

async function updateSystemInfo() {
  try {
    const systemInfo = await fetchJson(`${API}/system-info`);
    settingsState.systemInfo = systemInfo;
    
    // 只更新当前显示的部分
    if (settingsState.currentSection === 'system') {
      updateSystemInfoDisplay();
    }
    
    // 更新设备部分的内存信息
    if (settingsState.currentSection === 'device') {
      updateDeviceMemoryDisplay();
    }
    
  } catch (error) {
    console.error('更新系统信息失败:', error);
  }
}
```

### 设置缓存
```javascript
// 缓存设置值，减少API调用
const settingsCache = {
  data: null,
  timestamp: 0,
  ttl: 30000 // 30秒
};

async function getCachedSettings() {
  const now = Date.now();
  
  if (settingsCache.data && (now - settingsCache.timestamp < settingsCache.ttl)) {
    return settingsCache.data;
  }
  
  const settings = await fetchJson(`${API}/settings`);
  settingsCache.data = settings;
  settingsCache.timestamp = now;
  
  return settings;
}
```

## 错误处理

### 设置保存错误处理
```javascript
async function saveSettingsWithRetry(settings, maxRetries = 3) {
  let lastError;
  
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      
      const result = await response.json();
      
      if (result.ok) {
        return result;
      } else {
        throw new Error(result.error || '保存失败');
      }
      
    } catch (error) {
      lastError = error;
      
      if (i < maxRetries - 1) {
        // 等待后重试
        await sleep(1000 * Math.pow(2, i));
        continue;
      }
    }
  }
  
  throw lastError;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

### 设备切换回退
```javascript
async function safeDeviceSwitch(device) {
  const originalDevice = settingsState.modelInfo.device;
  
  try {
    await switchDevice(device);
  } catch (error) {
    // 切换失败，恢复到原始设备
    console.error('设备切换失败，恢复原始设置:', error);
    
    // 更新UI显示
    document.querySelector(`input[value="${originalDevice}"]`).checked = true;
    
    // 显示错误信息
    showError(`设备切换失败: ${error.message}`);
    
    // 尝试重新加载当前设备信息
    try {
      const modelInfo = await fetchJson(`${API}/model-info`);
      settingsState.modelInfo = modelInfo;
      updateDeviceDisplay();
    } catch (reloadError) {
      console.error('重新加载设备信息失败:', reloadError);
    }
  }
}
```

## 扩展性设计

### 设置项注册
```javascript
// 允许插件注册自定义设置项
window.settingsRegistry = window.settingsRegistry || {
  sections: [],
  settings: []
};

function registerSettingsSection(section) {
  window.settingsRegistry.sections.push(section);
  rebuildSettingsNav();
}

function registerSetting(setting) {
  window.settingsRegistry.settings.push(setting);
  rebuildSettingsForms();
}
```

### 自定义验证规则
```javascript
// 设置值验证
const settingValidators = {
  device: (value) => ['cpu', 'cuda'].includes(value),
  theme: (value) => ['light', 'dark', 'auto'].includes(value),
  log_level: (value) => ['debug', 'info', 'warning', 'error'].includes(value),
  font_size: (value) => ['small', 'medium', 'large', 'x-large'].includes(value)
};

function validateSetting(key, value) {
  const validator = settingValidators[key];
  if (validator) {
    return validator(value);
  }
  return true; // 没有验证器则默认通过
}

function registerSettingValidator(key, validator) {
  settingValidators[key] = validator;
}
```

## 相关模块
- **Overview模块**: 显示系统状态概览
- **Model模块**: 模型加载和管理
- **Logger模块**: 日志级别配置
- **Storage模块**: 存储空间管理

---

*最后更新: 2026-04-29*