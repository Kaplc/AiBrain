# 工作记忆模块 —— WorkMemory

## 一、项目目标

- **项目名称**：工作记忆模块（WorkMemory）
- **一句话描述**：在 `backend/modules/brain/memory/workmemory/` 下统一管理工作记忆，`data/` 子目录存放 `.md` 文件，`workmemory.py` 提供 CRUD + 搜索接口，供 LLM Agent 和流水线步骤读写临时上下文。
- **核心目标**：
  1. 文件管理：对 `data/` 目录下的 `.md` 文件进行增删改查
  2. 内容搜索：基于关键词匹配搜索工作记忆内容
  3. Agent 集成：LLM Agent 可通过 `WorkMemoryManager` 读写工作记忆
- **不做的事**：
  - 不替代 mem0 长期记忆
  - 不做文件版本控制
  - 不限制文件格式（但推荐 `.md`）

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| 无短期记忆 | mem0 是长期向量库，无法快速读写临时上下文 | Agent 没有"便利贴" |
| 无文件视角 | 无法直接查看和编辑 AI 的中间状态 | 调试困难 |
| Agent 无工作区 | 处理复杂任务时没有暂存中间结果的地方 | 上下文窗口溢出 |

### 2.2 目标场景

```
场景1：Agent 暂存中间结果
  → WorkMemoryManager.write("analysis.md", "结论：...")
  → 后续步骤读取继续处理

场景2：用户手动编辑
  → 在 data/ 下创建 .md 写入提示词
  → Agent 启动时读取使用

场景3：搜索工作记忆
  → 关键词匹配所有 .md 文件
  → 返回匹配结果
```

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 文件 CRUD | 创建/读取/更新/删除 .md 文件 | **P0** | 文件系统操作 |
| 文件注册 | 数据目录下已有的 .md 文件自动注册到管理器，写时自动注册新文件/扫目录更新列表 | **P0** | 写/删后主动刷新注册表 |
| 内容搜索 | 按关键词搜索文件名和内容 | **P0** | 子串匹配 |
| 列表查询 | 列出所有已注册的工作记忆文件（含元数据） | **P0** | 文件名、大小、修改时间 |
| input 滚动写入 | 向 `input.md` 增量追加内容，超过 20 条时自动删除最旧条目 | **P0** | `input_mem_write()`，固定长度滚动缓冲区 |
| input 专用读取 | 读取 `input.md` 全部内容，按条目解析返回结构化列表 | **P0** | `input_mem_read()`，返回 [{seq, content}, ...] |
| package 专用写入 | 写入内容到 `package.md`（覆盖） | **P0** | `package_mem_write(content)` |
| package 专用读取 | 读取 `package.md` 全部内容 | **P0** | `package_mem_read()`，返回 str |
| Agent 处理指令 | 通过 LLM Agent 解析自然语言指令，自动执行添加/删除工作记忆 | **P0** | 核心功能，调 AgentManager |
| package 记忆搜索 | 读取 input.md 全部条目作为 query，搜索长期记忆，结果写入 package.md | **P0** | `handle_packagemem()`，桥接工作记忆与 mem0 |

---

## 四、非功能需求

- **轻量**：纯文件系统操作，无额外依赖
- **路径安全**：防止路径穿越攻击
- **编码统一**：UTF-8
- **单例**：与现有模块风格一致

---

## 五、系统架构

### 5.1 目录结构

```
backend/modules/brain/memory/workmemory/
├── __init__.py       # 导出 WorkMemoryManager
├── workmemory.py     # WorkMemoryManager 单例实现
└── data/             # .md 文件存储目录
    ├── .gitkeep
    ├── 当前任务.md
    ├── 分析记录.md
    └── ...
```

### 5.2 模块结构

```
workmemory/
├── __init__.py     → from .workmemory import WorkMemoryManager, get_work_memory
├── workmemory.py   → WorkMemoryManager 单例
│                      - _registry: dict[str, FileInfo]   ← 注册表
│                      - _scan_directory()                ← 启动时扫描构建
│                      - list() / read() / write() / delete() / search()
│                      - process_instruction()
└── data/           → .md 文件（纯文本，UTF-8）
```

### 5.3 关键设计决策

1. **目录即边界**：`data/` 是固定存储根目录，所有路径拼接基于此，防止穿越
2. **文件即记录**：每个 `.md` 文件就是一条工作记忆，文件名是唯一 ID
3. **默认文件**：`data/input.md`（滚动记忆）和 `data/package.md`（固定记忆）默认存在。write() 未指定文件名时默认写入 `input.md`
4. **注册表驱动**：管理器启动时扫描 `data/` 构建注册表；每次 write/delete 后自动刷新对应条目，不依赖实时文件扫描
5. **input.md 滚动缓冲区**：`input.md` 以 `---` 分隔条目，`input_mem_write(content)` 追加到末尾，超过 20 条时删最旧的。每条格式为 `\n## 条目 {n}\n{content}\n---`
5. **单例管理**：`WorkMemoryManager.get_instance()` 获取
6. **Agent 驱动增删**：`process_instruction(instruction)` 方法接收自然语言指令，内部调 `AgentManager.get("work_memory")` 让 LLM 解析指令意图（添加/删除/查询），再调用对应的 CRUD 方法执行

---

## 六、数据结构

### 6.1 注册表（内存）

```python
# 管理器内部的注册表
_registry: dict[str, FileInfo] = {}  # key=文件名, value=FileInfo

@dataclass
class FileInfo:
    name: str           # "当前任务.md"
    size: int           # 字节
    created_at: float   # 时间戳
    modified_at: float  # 时间戳
```

启动时 `_scan_directory()` 扫描 `data/` 下所有 `.md` 文件写入 `_registry`。write/delete 后自动刷新。

### 6.2 对外返回的元数据

```python
{
    "name": "当前任务.md",
    "size": 1024,
    "modified_at": "2026-06-07T10:30:00",
    "created_at": "2026-06-07T09:00:00",
}
```

### 6.3 搜索匹配

```python
{
    "name": "当前任务.md",
    "matches": ["结论：...", "下一步：..."],
    "match_count": 2,
}
```

---

## 七、流程设计

### 0. 初始化（默认文件 + 扫描注册表）

```
WorkMemoryManager 首次 get_instance()
  → 确保 data/ 目录存在
  → 确保 data/input.md 和 data/package.md 存在（不存在则创建空文件）
  → _scan_directory()
  → 遍历 data/ 下所有 *.md
  → 读取文件信息（size, created_at, modified_at）
  → 写入 _registry[name] = FileInfo
  → 后续 list() 直接读 _registry，不再扫磁盘
```

### 1. 写入

```
Agent → wm.write("task.md", content)
  → 安全拼接路径（data/task.md）
  → 写入文件（UTF-8）
  → 刷新 _registry["task.md"] = FileInfo(...)
  → 返回元数据

省略文件名 → 默认写入 input.md：
  → wm.write("今天学了 Python")
    等价于 wm.write("input.md", "今天学了 Python")

### 1b. input 滚动写入（独立，不依赖通用 write）

```
Agent → wm.input_mem_write("今天学了 Python")
  → 直接操作文件系统：
    1. 读取 data/input.md 全部内容
    2. 以 --- 分隔解析出条目列表
    3. 在末尾追加新条目（格式：## 条目 {n}\n{content}\n---）
    4. 如果条目数 > 20，删除最旧的 excess 条
    5. 写回 data/input.md（UTF-8）
    6. 刷新 _registry 中的 input.md 元数据
  → 完全独立，不调 write()/read()/delete()
  → 返回 {total: 条目数, appended: "..", removed: 旧条目数}
```

### 1c. input 专用读取（独立，不依赖通用 read）

```
Agent → wm.input_mem_read()
  → 直接读取 data/input.md 全部内容
  → 以 --- 分隔解析出条目列表
  → 每条提取序号和正文
  → 返回 [{"seq": 1, "content": "..."}, {"seq": 2, "content": "..."}]
  → 文件不存在返回空列表
  → 完全独立，不调 read()
```

### 1d. package 专用读写（独立，不依赖通用 read/write）

```
Agent → wm.package_mem_write("新的结构化内容")
  → 直接覆盖写入 data/package.md（UTF-8）
  → 刷新 _registry
  → 返回 {name: "package.md", size: ...}

Agent → wm.package_mem_read()
  → 直接读取 data/package.md
  → 返回文件全部内容（str）
  → 文件不存在返回 ""
```

### 2. 删除

```
Agent → wm.delete("task.md")
  → 删除文件
  → 从 _registry 移除 "task.md"
  → 返回 True
```

### 3. 读取

```
Agent → wm.read("task.md")
  → 安全拼接 → 读取 → 返回内容
  → 不存在返回 None
```

### 4. 搜索

```
调用方 → wm.search("关键词")
  → 遍历 data/ 下所有 .md
  → 子串匹配文件名 + 内容
  → 返回匹配结果列表
```

### 5. Agent 处理指令

```
调用方 → wm.process_instruction("记录一下当前的进度")
  → 调 AgentManager.get("work_memory").run(instruction)
  → LLM 解析指令意图：
     - "添加/更新" → 决定文件名 + 内容 → wm.write(name, content)
     - "删除" → 决定文件名 → wm.delete(name)
     - "查询" → 决定关键词 → wm.search(keyword)
  → 返回操作结果
```

> `work_memory` Agent 注册在 `LLM/Agents/` 下，与 `entity_extract` 等其他 Agent 并列。

### 6. get_workmem 打包读取（占位）

```
调用方 → wm.get_workmem()
  # TODO: 合并 input_mem_read + package_mem_read
  # 返回 {"input": [{seq, content}], "package": "str"}
  ...
```

### 7. package 记忆搜索

```
调用方 → wm.handle_packagemem()
  1. input_mem_read() 获取 input.md 所有条目内容
  2. 合并为 query 文本
  3. 调 core.search_memory(query) 搜索长期记忆
  4. 将搜索结果格式化为 Markdown
  5. package_mem_write(formatted) 写入 package.md
  → 返回 {query, result_count, package_size}
```

> 桥接工作记忆与长期记忆：input.md 的滚动内容作为搜索线索，找到的长期记忆写入 package.md 供后续使用。

```python
from modules.brain.memory.workmemory import get_work_memory

wm = get_work_memory()

# 直接文件操作
wm.write("task.md", "# 任务说明\n\n1. 完成记忆流水线")
content = wm.read("task.md")

# 省略文件名 → 默认写入 input.md
wm.write("今天学了 Python")  # 等价于 wm.write("input.md", "今天学了 Python")

# input 滚动写入（独立方法）
result = wm.input_mem_write("志远帮我升级了系统")
# → 超出 20 条自动删最旧
# → {"total": 12, "appended": "志远帮我升级了系统", "removed": 0}

# input 专用读取（独立方法）
entries = wm.input_mem_read()
# → [{"seq": 1, "content": "今天学了 Python"}, {"seq": 2, "content": "志远帮我升级了系统"}]

# package 专用读写（独立方法）
wm.package_mem_write("# 项目说明\n\n这是 package 内容")
content = wm.package_mem_read()

# package 记忆搜索（从 input.md 查长期记忆写入 package.md）
result = wm.handle_packagemem()
# → {"query": "志远帮我升级了系统 今天学了 Python", "result_count": 5, "package_size": 2048}

# write() 是通用的覆盖写入，和专用方法互不影响
wm.write("其他笔记.md", "一些记录")

results = wm.search("流水线")  # 搜索所有文件
files = wm.list()             # 列出所有已注册文件
wm.delete("task.md")

# Agent 驱动（自然语言指令）
result = wm.process_instruction("把当前的进度记录到任务.md中：记忆流水线已完成")
# → LLM 解析并调用 wm.write("任务.md", "当前进度：\n- 记忆流水线已完成")

result = wm.process_instruction("删除所有关于旧方案的工作记忆")
# → LLM 解析并调用 wm.search("旧方案") + wm.delete() 循环
```

---

## 九、验收标准

| 编号 | 验收项 | 操作 | 预期结果 |
|------|--------|------|---------|
| A1 | 写入文件 | `write("test.md", "# Hello")` | 文件创建在 data/ 下 |
| A2 | 读取文件 | `read("test.md")` | 返回内容 |
| A3 | 文件不存在 | `read("none.md")` | 返回 None |
| A4 | 路径穿越防御 | `write("../../etc/passwd", "...")` | 拒绝写入 |
| A5 | 列出文件 | `list()` | 包含 test.md |
| A6 | 搜索 | `search("Hello")` | 返回匹配 |
| A7 | 删除文件 | `delete("test.md")` | 返回 True |
| A8 | 单例 | `get_work_memory() is get_work_memory()` | True |
| A9 | Agent 处理添加指令 | `process_instruction("记录进度：已完成")` | 文件被创建/更新，内容包含"已完成" |
| A10 | Agent 处理删除指令 | `process_instruction("删除测试文件")` | 对应文件被删除 |

---

## 十、开发任务拆分

| 任务 ID | 任务名称 | 依赖 | 复杂度 | 预估代码量 | 所属模块 |
|---------|----------|------|--------|-----------|---------|
| T001 | 创建 workmemory/ + data/ 目录 + .gitkeep | 无 | S | — | workmemory/ |
| T002 | WorkMemoryManager 实现（list/read/write/delete/search + 路径安全） | 无 | M | ~100 行 | workmemory.py |
| T003 | process_instruction 方法（调 AgentManager 解析指令 + 执行 CRUD） | T002 | M | ~40 行 | workmemory.py |
| T004 | input_mem_write + input_mem_read（解析条目、20 条上限、删旧滚动） | T002 | M | ~70 行 | workmemory.py |
| T005 | package_mem_write + package_mem_read | T002 | S | ~30 行 | workmemory.py |
| T006 | handle_packagemem（读 input.md → 搜 mem0 → 写 package.md） | T002 | M | ~50 行 | workmemory.py |
| T007 | __init__.py 导出 | T002 | S | ~10 行 | __init__.py |

**预估工作量**：约 2-3 小时，~200 行代码
