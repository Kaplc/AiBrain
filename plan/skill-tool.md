# Skill 工具（LLM function calling）

## 一、项目目标

- **项目名称**：Skill 工具
- **一句话描述**：在 Tool Loop 中添加一个 `skill` 工具，让 LLM 可以在对话中列出可用技能并加载技能内容作为上下文
- **核心目标**：
  1. 扫描 `.aibrain/skills/` 目录，识别所有技能
  2. 按名称加载指定技能的 SKILL.md 内容，返回给 LLM
  3. 遵循现有的 ToolDef 注册模式，在 app.py 启动时注册
- **不做的事**：
  - 不实现技能执行（Skill 工具只加载内容，不执行技能）
  - 不修改 Tool Loop 的核心逻辑
  - 不修改现有技能文件

## 二、业务背景

- **问题现状**：
  - 当前 AiBrain 有多个技能（SKILL.md）存放在各目录，但 LLM 无法在对话中主动加载
  - LLM 只能被动等待提示词中加载技能，无法按需索取
  - Tool Loop 已有 8 个工具，但缺少技能相关工具
- **目标用户**：使用 AiBrain Tool Loop 的 LLM
- **预期价值**：
  - LLM 可以按需加载技能，响应更精准
  - 技能库的利用率更高
  - 与其他工具（如 `memory_search`）形成互补

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| 列出技能 | 作为 LLM，我想列出所有可用技能，以便知道我能调用什么 | P0 | 返回技能名称+描述列表 |
| 加载技能 | 作为 LLM，我想按名称加载一个技能的完整内容，以便按技能指导完成任务 | P0 | 返回完整内容（≤20000 字符） |
| 路径安全 | 作为用户，我不希望技能工具能读取技能目录以外的文件 | P0 | `os.path.realpath` 前缀校验 |

## 四、非功能需求

- **性能要求**：技能列表扫描 < 100ms，技能内容加载 < 50ms
- **可用性要求**：技能目录不存在时降级为空列表，不抛异常
- **可维护性要求**：遵循现有 `file_tools.py` / `memory_tools.py` 的代码模式

## 五、系统架构

### 调用流程

```mermaid
sequenceDiagram
    participant LLM as LLM
    participant Loop as Tool Loop
    participant Tool as skill_tools.py
    participant FS as 文件系统

    LLM->>Loop: tool_call(skill, {action:"load", name:"skl-test"})
    Loop->>Tool: execute("skill", {action:"load", name:"skl-test"})
    Tool->>FS: 扫描 .aibrain/skills/
    Tool->>FS: 读取 skl-test/SKILL.md
    FS-->>Tool: SKILL.md 内容
    Tool-->>Loop: 格式化的 skill_content
    Loop-->>LLM: tool_result → LLM 上下文
```

### 目录结构变化

```
backend/modules/LLM/tools/
  ├── __init__.py          # 无变化
  ├── registry.py          # 无变化
  ├── file_tools.py        # 无变化
  ├── memory_tools.py      # 无变化
  ├── plan_tools.py        # 无变化
  └── skill_tools.py       # 新增 — Skill 工具
backend/app.py             # + register_skill_tools() 调用
```

### 技术栈

| 层 | 技术 | 理由 |
|---|------|------|
| 工具定义 | ToolDef | 遵循现有模式 |
| 文件扫描 | pathlib / os.listdir | 轻量，无需第三方 |
| YAML 解析 | `yaml.safe_load()` | venv 已安装 pyyaml 6.0.3，标准 YAML 解析 |
| 路径安全 | os.path.realpath 前缀检查 | 参考 file_tools.py |

### 关键设计决策

1. **单工具双 action**：采用 `skill` 单工具 + `action` 参数区分 list/load，减少工具注册数
2. **参数设计**：`action` 必选，`name` 仅在 load 时必选
3. **技能目录**：只扫描 `.aibrain/skills/`
4. **文件扫描方式**：扫描 `*/SKILL.md`，用轻量解析器提取 frontmatter 的 name 和 description
5. **内容截断**：skill_load 返回最多 20000 字符，超出截断并提示（参考 plan_tools.py）
6. **YAML 解析**：用 `yaml.safe_load()`（pyyaml 6.0.3，已在 venv），原生支持三种 frontmatter 格式：
   - 简单键值：`key: value`
   - 区块标量（`|`）：保留换行
   - 折叠标量（`>`）：合并为一段

## 六、数据结构

### 技能目录布局

```
{project_root}/
  └── .aibrain/skills/skl-xxx/SKILL.md
```

### SKILL.md 格式（YAML frontmatter）

```yaml
---
name: skl-xxx
description: 技能描述（支持 > 折叠块和 | 保留换行块）
---
技能正文 Markdown 内容
```

### 返回格式

**skill_list 返回**：
```
可用技能（共 3 个）：
  skl-test - 测试技能
  skl-doc-memory - 文档记忆技能
  skl-project-planner - 项目计划技能
使用 skill_load 并指定 name 加载技能完整内容
```

**skill_load 返回**：
```
<skill_content name="skl-test">
# SKILL.md 完整内容（最多 20000 字符）
</skill_content>
```

## 七、流程设计

### 核心流程

```mermaid
graph TD
    A[LLM 调用 skill 工具] --> B{action}

    B -->|list| C[扫描 .aibrain/skills/]
    C --> D[读取每个 SKILL.md 的 frontmatter]
    D --> F[返回格式化列表]

    B -->|load| G[校验 name 参数]
    G --> H[在 .aibrain/skills/ 中按名称匹配]
    H --> I{找到?}
    I -->|是| J[读取 SKILL.md 完整内容]
    J --> K[超 20000 字符?]
    K -->|是| L[截断 + 提示]
    K -->|否| M[原样返回]
    L --> N[返回 skill_content 格式]
    M --> N
    I -->|否| O[返回"未找到技能: xxx"]
```

### 异常流程

- **技能目录不存在**：降级为空列表
- **SKILL.md 缺少 frontmatter**：用目录名作为技能名，描述置空
- **frontmatter 解析失败**：用目录名兜底，不阻塞
- **请求的技能不存在**：返回 `未找到技能: 名称`
- **路径穿越**：`os.path.realpath` 校验拒绝
- **读取文件失败**：返回错误信息

## 八、API 设计

无需新增外部 API。仅新增 ToolRegistry 内部工具。

### 内部工具定义

```
工具名: skill
描述: List available skills or load a skill's content by name.
参数:
  action: "list" | "load"  (必填)
  name: string             (action=load 时必填，要加载的技能名称)
```

## 九、验收标准

### 功能验收

1. **skill_list**：调用后返回列表中至少包含 `.aibrain/skills/` 下已安装的技能
2. **skill_load**：加载指定技能返回完整内容（≤20000 字符）
3. **不存在技能**：返回 `未找到技能: xxx`
4. **路径安全**：尝试 `../` 穿越路径被拒绝
5. **技能目录不存在**：删除目录后 list 不抛异常

### 代码验收

6. 代码模式与 `file_tools.py` / `memory_tools.py` 一致
7. 在 `app.py` 中注册
8. `_PROJECT_ROOT` 从 `../../../../` 计算正确

## 十、开发任务拆分

| ID | 任务名称 | 依赖 | 复杂度 | 模块 | 对应需求 |
|----|---------|------|--------|------|---------|
| S001 | 创建 skill_tools.py（frontmatter 解析 + 扫描 + 列表 + 加载） | — | S | 后端/LLM/tools | 全部功能 |
| S002 | 在 app.py 注册 register_skill_tools | S001 | S | 后端 | 集成 |
| S003a | 测试：正常路径（已知技能 list + load） | S002 | S | — | 验收1-2 |
| S003b | 测试：异常路径（不存在技能 + 路径穿越 + 无目录） | S002 | S | — | 验收3-5 |
