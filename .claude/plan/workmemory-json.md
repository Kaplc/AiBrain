# 工作记忆 JSON 化改造

## 一、项目目标

- **项目名称**：工作记忆 JSON 化改造（WorkMemory JSON）
- **一句话描述**：将 `backend/modules/brain/memory/workmemory/data/` 下的 `input.md` 和 `package.md` 改为 `input.json` 和 `package.json`，用 JSON 格式替代 Markdown 自定义解析。
- **核心目标**：
  1. 存储格式从 `.md` 改为 `.json`，消除 `---` 分隔符的自定义解析
  2. 数据结构化保存，读写无信息损失
  3. 保持外部接口签名完全不变（`input_mem_read/write`、`package_mem_read/write`、`get_workmem` 等）
  4. 更新所有消费方（pipeline memory section 等）
- **不做的事**：
  - 不改变工作记忆的业务逻辑（滚动 20 条、handle_packagemem 流程不变）
  - 不做数据迁移（input.md 和 package.md 是临时数据，首次写入时自动覆盖）
  - 不新增功能

---

## 二、业务背景

### 2.1 问题现状

| 问题 | 表现 | 影响 |
|------|------|------|
| 自定义解析 | `input.md` 用 `---` 分隔条目，`_parse_entries()` 自己写 split 逻辑 | 边缘情况（条目内含 `---`）解析错误 |
| 结构化丢失 | 读→写循环中 `---` 分隔的条目信息可能丢失 | `input_mem_read` 的解析与 `input_mem_write` 的序列化不一致 |
| 消费方需再解析 | `pipeline/sections/memory.py` 从 `package.md` 读取后再次用 `---` split | 格式耦合，改格式必须同步改所有消费方 |

### 2.2 目标

```
改前: input.md → `---` 分隔的 markdown → _parse_entries 解析
改后: input.json → `[{"seq":1, "content":"...", "time":"..."}]` → json.loads

改前: package.md → `---` 分隔的记忆文本 → pipeline 再 split
改后: package.json → `{"results":[...], "query":"..."}` → json.loads
```

---

## 三、功能需求

| 功能 | 用户故事 | 优先级 | 备注 |
|------|---------|--------|------|
| input.json 存储 | 作为系统，我用 JSON 数组存储 input 条目，无需自定义解析 | **P0** | 替换 input.md |
| package.json 存储 | 作为系统，我用 JSON 对象存储 package 搜索结果 | **P0** | 替换 package.md |
| 接口兼容 | 作为外部调用方，我不关心存储格式，`input_mem_read/write` 返回值不变 | **P0** | 返回 dict 格式不变 |

---

## 四、非功能需求

无特殊要求。

---

## 五、系统架构

### 5.1 目录结构

```
workmemory/data/
├── input.json       ← 改前: input.md
└── package.json     ← 改前: package.md
```

### 5.2 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/modules/brain/memory/workmemory/workmemory.py` | 存储和解析从 markdown 改为 JSON |
| `backend/modules/chat/pipeline/sections/memory.py` | 从 JSON 读取 package 结果，去掉 `---` split |

---

## 六、数据结构

### input.json

```json
[
  {"seq": 1, "content": "用户的第一条输入", "time": "2026-06-08 10:00"},
  {"seq": 2, "content": "用户的第二条输入", "time": "2026-06-08 10:05"}
]
```

### package.json

```json
{
  "query": "搜索关键词",
  "results": [
    {"id": "mem_xxx", "text": "记忆内容", "score": 0.92}
  ]
}
```

---

## 七、流程设计

### 7.1 input_mem_write（改后）

```
1. 读 input.json（不存在则 []）
2. json.loads 解析
3. 追加新条目 {seq, content, time}
4. 超 20 条删最旧
5. json.dumps 写回
```

### 7.2 pipeline memory 段（改后）

```
1. 读 package.json
2. json.loads 解析 → 取 results 数组
3. 遍历 results 取 text 字段
4. 格式化为 prompt 片段
```

---

## 八、API 设计

无新增 API。所有接口返回格式不变。

---

## 九、验收标准

1. `input_mem_write("hello")` → `input.json` 内容为合法 JSON 数组
2. `input_mem_read()` → 返回 `[{seq, content, time}, ...]`，与原格式一致
3. `package_mem_write(content)` → `package.json` 内容为合法 JSON
4. `package_mem_read()` → 返回 JSON 内容
5. `handle_packagemem()` → 搜索结果写入 `package.json`，格式正确
6. Pipeline memory section 能正确读取 `package.json` 并生成 prompt
7. 连续读写 100 轮，无数据丢失

---

## 十、开发任务拆分

| ID | 任务 | 依赖 | 复杂度 | 模块 | 对应需求 |
|----|------|------|--------|------|---------|
| T001 | `workmemory.py` 改造：`input_mem_read/write` 改用 JSON | — | M | workmemory | 功能需求 |
| T002 | `workmemory.py` 改造：`package_mem_read/write` 改用 JSON | — | S | workmemory | 功能需求 |
| T003 | `workmemory.py` 改造：`write()` / `read()` / `search()` 适配 .json | T001 | S | workmemory | 功能需求 |
| T004 | `workmemory.py` 改造：`handle_packagemem()` 输出 JSON 格式 | T002 | S | workmemory | 功能需求 |
| T005 | `pipeline/sections/memory.py` 改从 JSON 读取 | T004 | S | pipeline | 功能需求 |
| T006 | `_scan_directory()` 改为扫描 `*.json` | T001 | S | workmemory | 功能需求 |
| T007 | 删除旧 `.md` 文件（自动或首次写入覆盖） | T006 | S | workmemory | 功能需求 |
