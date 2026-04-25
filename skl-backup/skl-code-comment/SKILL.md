---
name: skl-code-comment
description: |
  为JavaScript代码添加逻辑说明性注释，描述函数的实现逻辑和步骤。
  当用户想要：
  - 为代码添加注释（"加上注释"、"写一下注释"）
  - 解释代码逻辑（"这个函数做什么"、"帮我理解这段代码"）
  - 规范注释风格（"按这个格式写注释"、"用这个注释风格"）
  请务必使用此技能！
---

# 代码注释技能 (skl-code-comment)

为JavaScript代码添加逻辑说明性注释，描述**函数的实现逻辑和步骤**，而非简单的功能说明。

---

## 核心设计原则

注释应该描述**怎么做**和**为什么这样做**，而不是**做了什么**：
- 描述函数的实现流程和步骤
- 说明调用关系和数据流向
- 标注关键逻辑和边界情况
- 用"流程："或"作用："引导具体实现

---

## 注释规范

### 注释结构

每个函数注释包含以下部分：

```javascript
/* ==================== 函数分类 ==================== */
// 函数名：简述功能
// 流程：步骤1 → 步骤2 → 步骤3
// 参数：参数名-含义
// 返回：返回值的含义
function funcName() {
  // 实现代码
}
```

### 注释模板

```javascript
/* ==================== 变量声明 ==================== */
// 变量名：用途说明
var myVar = value;

/* ==================== 功能分组 ==================== */
// 函数名：做什么
// 流程：获取输入 → 处理 → 返回结果
// 错误处理：发生时显示什么提示
async function myFunction() {
  const input = getInput();        // 获取输入
  if (!input) return;              // 空值校验
  try {
    const result = await api();    // 调用API
    updateUI(result);              // 更新界面
  } catch(e) {
    showError(e);                  // 错误处理
  }
}
```

### 关键模式

#### 1. 事件监听类
```javascript
// 监听键盘事件：检测是否按下某键，是则调用某函数
// 流程：keydown事件 → 检测按键 → functionName()
element.addEventListener('keydown', e => {
  if (e.key === 'Enter') functionName();
});
```

#### 2. API调用类
```javascript
// 调用某接口获取数据，失败时使用兜底方案
// 流程：fetch POST → 解析JSON → 成功更新UI，失败显示错误
async function fetchData() {
  try {
    const r = await fetch(API + '/path', {method:'POST', body: JSON.stringify(data)});
    const json = await r.json();
    updateUI(json);
  } catch(e) {
    showToast('操作失败');
  }
}
```

#### 3. 数据渲染类
```javascript
// 将数据数组渲染为HTML列表，显示在某元素中
// 流程：获取容器 → 遍历数据 → 生成HTML字符串 → 设置innerHTML
function renderList(items) {
  const el = document.getElementById('list');
  el.innerHTML = items.map(item => `<div>${item.name}</div>`).join('');
}
```

#### 4. 防抖/节流类
```javascript
// 设置延迟定时器，实现防抖效果（最后一次操作后才执行）
// 用于：避免快速连续操作（如搜索输入）时频繁触发
function debounce() {
  clearTimeout(timer);   // 清除之前的定时器
  timer = setTimeout(func, delay);  // 设置新的延迟定时器
}
```

#### 5. 状态管理类
```javascript
// 标记当前状态，用于区分不同模式的显示逻辑
// 流程：设置状态变量 → 各函数根据状态决定渲染内容
var currentMode = '';  // 当前模式：空值=默认状态，'search'=搜索模式

function onSearch() {
  currentMode = 'search';  // 标记为搜索模式
  renderResults();         // 渲染搜索结果
}
```

---

## 快速参考

| 场景 | 注释重点 |
|------|---------|
| 事件监听 | 检测什么条件，触发什么函数 |
| API调用 | 调用什么接口，失败怎么办 |
| 数据渲染 | 遍历什么，生成什么HTML |
| 状态标记 | 什么状态值，影响什么逻辑 |
| 工具函数 | 如何实现，边界情况 |

---

## 注意事项

- 注释位于函数定义上方，与函数之间留一个空行
- 变量声明的注释放在文件顶部的单独区块
- 保持注释简洁，每条说明控制在一行内
- 更新代码时同步更新注释