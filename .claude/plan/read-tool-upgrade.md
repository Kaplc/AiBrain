# read_file 工具升级 — 对齐 OpenCode read

## 一、项目目标

- **项目名称**：read_file 工具升级
- **一句话描述**：将 AiBrain 的 `read_file` 工具升级到与 OpenCode `read` 工具同等能力
- **核心目标**：
  1. 字节上限 + 行长截断，防止异常内容撑爆
  2. 支持绝对路径 + 相对路径
  3. 文件不存在时模糊匹配推荐
  4. 合并目录读取功能（替代独立的 `list_directory`）
  5. 二进制文件检测
  6. 输出格式对齐 XML 标签封装 + 精确分页提示
- **不做的事**：
  - 不实现 LSP 预热（无 LSP 基础设施）
  - 不实现图片/PDF 附件（无多模态需求）
  - 不实现权限校验（AiBrain 无权限系统）
  - 不修改 `list_directory` 工具（保留兼容）

## 二、业务背景

- **问题现状**：
  - `read_file` 没有字节上限，500 行长文件可撑爆 LLM 响应
  - 不支持绝对路径，LLM 只能用相对路径
  - 文件不存在只有简单报错，没有模糊匹配
  - 读取目录需要单独调用 `list_directory`，多一次工具调用
  - offset 从 0 开始不直观（OpenCode 从 1 开始）
  - 输出没有结构化封装，行号格式固定
- **目标用户**：使用 Tool Loop 的 LLM
- **预期价值**：
  - 读取更安全（字节上限防撑爆）
  - 读取更准（路径容错 + 模糊匹配）
  - 读取更少（目录合并免去一次工具调用）

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 字节上限 | 作为 LLM，我读取大文件时响应不会被截断丢失 | P0 | 50KB 硬上限（最终输出 UTF-8 字节数） |
| 行长截断 | 作为 LLM，我不会因为某行过长而卡死 | P0 | 每行 2000 字符截断 |
| 绝对路径 | 作为 LLM，我可以用绝对路径读任何文件 | P0 | 自动兼容相对路径 |
| 模糊推荐 | 作为 LLM，我打错文件名时能获得近似推荐 | P1 | 最多 3 个候选，限邻近目录 |
| 目录读取 | 作为 LLM，我读目录路径时直接列出内容 | P1 | 合并 `list_directory` |
| 二进制检测 | 作为 LLM，我读二进制文件时不会被乱码糊脸 | P1 | 4KB 采样检测 |
| 输出封装 | 输出结构化，含 path/type/content 标签 | P2 | 对齐 OpenCode 格式 |
| 分页精确 | 分页提示精确到 `Use offset=N to continue.` | P2 | 对齐 OpenCode |

## 四、非功能需求

- **性能要求**：读取 < 50ms（小文件），< 200ms（大文件截断）
- **兼容性**：升级后旧参数名称（`path`、`max_lines`）在 schema 中继续声明（标记 deprecated），不破坏已有调用
- **稳定性**：字节上限不抛出异常，只截断输出

## 五、系统架构

### 文件变更

```
backend/modules/LLM/tools/
  ├── __init__.py          # 无变化
  ├── registry.py          # 无变化
  ├── file_tools.py        # 修改 — read_file 升级
  ├── memory_tools.py      # 无变化
  ├── plan_tools.py        # 无变化
  └── skill_tools.py       # 无变化
```

### 调用流程

```mermaid
graph TD
    A[LLM 调用 read_file] --> B{路径是文件还是目录?}
    B -->|文件| C[绝对/相对 → 解析完整路径]
    C --> D[路径安全检查]
    D --> E{文件存在?}
    E -->|是| F[读取前 4KB 采样]
    F --> G{二进制?}
    G -->|是| H[返回"二进制文件不可读"]
    G -->|否| I[逐行读取 + 截断 + 计字节]
    I --> J[返回 XML 格式结果]

    E -->|否| K[fuzzy_match 模糊匹配]
    K --> L{找到近似?}
    L -->|是| M[推荐候选文件]
    L -->|否| N[返回"文件不存在"]

    B -->|目录| O[列出目录内容 + 分页]
    O --> J
```

### 关键设计决策

1. **函数参数用 snake_case**：函数签名使用 `file_path`、`limit`、`offset`，与 file_tools.py 现有惯例一致。schema 中声明 `file_path`（不用 `filePath`），因为 ToolDef.fn(**args) 直接解包 schema 参数名
2. **兼容旧参数**：schema 中同时声明 `path`（deprecated）和 `max_lines`（deprecated）作为别名，LLM 仍可传入旧参数名。函数内部 `file_path = path or file_path` 映射
3. **`limit=0` 保留"全部读取"语义**：兼容旧 `max_lines=0` 行为。新默认值 `limit=2000`，但传 `limit=0` 时读取全部
4. **offset 从 1 开始，offset=0 视为 1**：schema description 中明确写 `1-based`。收到 `offset=0` 时记录 `logger.warning` 并视为 1，以便检测旧调用
5. **字节上限 50KB**：严格按最终返回字符串 `output.encode("utf-8")` 计算字节数。含 XML 标签 + 行号前缀。`50KB = 50 * 1024`
6. **行长截断**：在行号前缀之后计算，超过 2000 字符截断加 `...` 标记
7. **目录读取**：根据 `os.path.isdir()` 判断，自动切换文件/目录模式。目录模式只列当前目录（不递归），支持 offset/limit 分页
8. **模糊匹配**：限定在用户输入文件所在目录搜索，排除 `node_modules/`/`.venv`/`__pycache__`/`.git`，1 秒超时

## 六、数据结构

### 参数

schema 声明（按 json schema 顺序）：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| file_path | string | 否（与 path 二选一） | — | 文件路径（绝对或相对项目根） |
| path | string | 否（deprecated） | — | 旧参数名，与 file_path 二选一 |
| limit | integer | 否 | 2000 | 最大返回行数（0=全部） |
| max_lines | integer | 否（deprecated） | — | 旧参数名，映射到 limit |
| offset | integer | 否 | 1 | 起始行号（**1 开头**）。向后兼容：offset=0 视为 1 |

### 输出格式（文件）

```
<path>{absolute_path}</path>
<type>file</type>
<content>
{offset}: {line1}
{offset+1}: {line2}
...

(Showing lines {offset}-{last} of {total}. Use offset={next} to continue.)
</content>
```

### 输出格式（目录）

```
<path>{directory_path}</path>
<type>directory</type>
<entries>
file1.py
file2.py
subdir/
...

(Showing 20 of 100 entries. Use 'offset' parameter to read beyond entry 21)
</entries>
```

### 输出格式（文件不存在 + 模糊推荐）

```
文件不存在: {filePath}

你是不是要找:
  /real/path/to/similar1.py
  /real/path/to/similar2.txt
```

### 输出格式（二进制文件）

```
二进制文件不可读: {path}
```

## 七、流程设计

### 核心流程

```
1. 解析参数
   - file_path ← file_path or path
   - limit ← max_lines if max_lines else limit（兼容旧参数）
   - offset ← offset | 1（offset=0 视为 1，log warning）
   - limit ← limit or total_lines（limit=0 表示全部）

2. 路径解析
   - 绝对路径 → 直接使用
   - 相对路径 → _PROJECT_ROOT / file_path
   - Windows 路径归一化

3. 安全检查（os.path.realpath 前缀校验）

4. 判断文件/目录
   - 目录 → list_directory_content(path, offset, limit)
   - 文件不存在 → fuzzy_match(path) → 推荐或报错
   - 文件存在 → 继续

5. 二进制检测（is_binary_file 辅助函数）
   - 4KB 采样
   - 发现 \x00 → 立即判二进制（硬判据）
   - 不可打印字符 > 30% → 判二进制

6. 逐行读取（read_file_lines 辅助函数）
   - 从 offset 开始，最多 limit 行
   - 每行超 2000 字符 → 截断 + "..."
   - 累计输出字节（utf-8）超 50KB → 停止，标记 cut
   - 行数超 limit → 停止，标记 more

7. 格式化输出（XML 标签 + 分页提示）
```

### 辅助函数拆分

| 函数 | 职责 | 代码量 |
|------|------|--------|
| `_is_binary_file(path)` | 4KB 采样 → 二进制判定 | ~20 行 |
| `_fuzzy_match_path(path)` | 模糊匹配文件名候选 | ~25 行 |
| `_list_directory_content(path, offset, limit)` | 目录条目列出 + 分页 | ~25 行 |
| `_read_file_lines(path, offset, limit)` | 逐行读取 + 截断 + 字节上限 | ~35 行 |
| `_read_file_fn(file_path, ...)` | 编排上述 4 个辅助函数 | ~60 行 |

### 异常流程

- **文件不存在 + 无模糊匹配**：返回 `文件不存在: {path}`
- **路径穿越**：返回 `不允许读取项目根以外的文件`
- **二进制文件**：返回 `二进制文件不可读: {path}`
- **offset 超行数**：返回空内容 + `(Offset {offset} is out of range, file has {total} lines)`
- **读取异常**：返回 `读取失败: {error}`
- **模糊匹配超时**：跳过推荐，直接返回"文件不存在"

## 八、API 设计

工具定义 schema：

```
工具名: read_file
描述: Read file contents (supports both absolute and project-relative paths).
       If the path is a directory, lists its contents.
       Automatically detects binary files and caps output at 50KB.

参数:
  file_path: string (可选) - 文件路径，支持绝对路径或相对项目根
  path: string (可选, 已弃用) - 旧参数名，与 file_path 二选一
  limit: integer (可选, 默认 2000) - 最大返回行数（0=全部）
  max_lines: integer (可选, 已弃用) - 旧参数名，映射到 limit
  offset: integer (可选, 默认 1) - 起始行号（1 开头）
```

## 九、验收标准

### 功能验收

1. **字节上限**：读取超过 50KB（UTF-8）的文件自动截断，标记 cut
2. **行长截断**：超 2000 字符的行被截断 + `...` 标记
3. **绝对路径**：传绝对路径成功读取
4. **路径兼容**：传旧 `path` 参数仍然工作
5. **模糊匹配**：输入 `backend/app.p` 推荐 `backend/app.py`
6. **目录读取**：传入目录路径直接列出条目（非递归）
7. **二进制检测**：传入 `.pyc` 文件返回 `二进制文件不可读`
8. **分页提示**：格式 `Use offset=N to continue.`，N 精确
9. **offset 从 1 开始**：传 offset=1 从第一行开始

### 回归验收

10. **旧参数不损坏**：`read_file(path="backend/modules/chat/loop.py", max_lines=50, offset=10)` 继续工作
11. **list_directory 不冲突**：两种目录读取方式并存，LLM 可选
12. **limit=0 读取全部**：传 `limit=0` 时返回完整文件

### 测试 checklist（R003 手动测试）

- [ ] 正常文件读取（纯文本，小文件）
- [ ] 大文件超出 50KB → 截断标记 cut
- [ ] 超长行（>2000 字符）→ 截断
- [ ] 绝对路径传入
- [ ] 旧参数 `path` + `max_lines` + `offset=0`
- [ ] 模糊匹配（接近的文件名）
- [ ] 目录路径 → 列出内容 + 分页
- [ ] `.pyc` 或其他二进制文件 → 返回提示
- [ ] 不存在的文件 → "文件不存在"
- [ ] 路径穿越 `../../` → 拒绝

## 十、开发任务拆分

| ID | 任务名称 | 依赖 | 复杂度 | 模块 | 对应需求 |
|----|---------|------|--------|------|---------|
| R001a | 新增 `_is_binary_file` 辅助函数 | — | S | 后端/file_tools.py | 二进制检测 |
| R001b | 新增 `_fuzzy_match_path` 辅助函数 | — | S | 后端/file_tools.py | 模糊推荐 |
| R001c | 新增 `_list_directory_content` 辅助函数 | — | S | 后端/file_tools.py | 目录读取 |
| R001d | 新增 `_read_file_lines` 辅助函数 | — | S | 后端/file_tools.py | 行读取+截断+字节 |
| R002 | 重写 `_read_file_fn` + 更新参数 schema（编排 R001a~d） | R001a~d | M | 后端/file_tools.py | 全部功能+兼容 |
| R003 | 手动测试 + 修复边界情况 | R002 | S | — | 验收 |
