# 替换 mem0 为自定义存储层

## 一句话目标

通过一个**统一接口层**解耦管线与后端存储，逐步用自定义存储替换 mem0，且未来可随时移除 mem0 而不影响管线。

## 核心架构：统一接口层

```
管线步骤                             统一接口层                        后端实现
─────────                           ────────                        ────────

vector_store ──→  memory_store()  ──┬──→ Qdrant 直连（新 collection）
                                     │        完整 payload：text + emotion + scene + temperature + hooks
vector_search ──→  memory_search() ──┤
                                     └──→ mem0（老 collection，只读）
                                               读取 data 字段，统一映射为 {id, text, score}
```

**管线只调 `memory_store()` / `memory_search()`，不关心后端是谁。**
**移除 mem0 时，删掉统一接口里的 mem0 分支即可，管线代码一行不改。**

---

## 架构优势

| 场景 | 怎么做 |
|------|--------|
| 新记忆存储 | 走 Qdrant 直连，完整 payload |
| 旧记忆搜索 | mem0_memories 只读，搜索时查询 |
| 未来移除 mem0 | 删统一接口里的 mem0 分支 + 删代码文件 |
| 新集旧搜合并 | 两个 collection 都查，结果合并返回 |
| 迁移老数据到新格式 | 跑一次批处理，不影响在线服务 |

---

## 实施步骤

### Step 1：统一接口层 — `backend/modules/brain/memory/store.py`

```python
def memory_store(text: str, payload: dict = None) -> dict:
    """统一存储接口
    
    Args:
        text: 记忆文本
        payload: 完整元数据（emotion, scene, temperature, hooks 等）
    
    Returns:
        {"result": ..., "stored_texts": [...], "added_count": ...}
    """
    # 当前只走 Qdrant 直连
    # 如果要支持多后端，在这里加分发逻辑
    return _store_qdrant(text, payload)


def memory_search(query: str, **kwargs) -> list[dict]:
    """统一搜索接口
    
    Returns:
        [{id, text, score, source, payload?}, ...]
    """
    results = []
    # 1. 搜新 collection
    results.extend(_search_new(query, **kwargs))
    # 2. 搜老 collection（mem0）
    results.extend(_search_legacy(query, **kwargs))
    # 3. 去重 + 排序
    return _merge_results(results)
```

接口内部对老数据做适配：
```python
def _search_legacy(query, **kwargs):
    """查 mem0_memories collection，把 data 字段映射为 text"""
    client = QdrantClient(...)
    vector = embed_texts([query])[0]
    hits = client.search("mem0_memories", query_vector=vector, ...)
    return [{
        "id": hit.id,
        "text": hit.payload.get("data", ""),  # ← mem0 的文本在 data 字段
        "score": round(hit.score, 4),
        "source": "semantic",
    } for hit in hits]
```

### Step 2：新建 `backend/modules/brain/memory/qdrant_store.py`

嵌入 + 存新 collection 的实现，被 `memory_store()` 调用：

```python
def embed_texts(texts: list[str]) -> list[list[float]]:
    """POST /encode → return vectors"""

def store_vectors(text: str, payload: dict) -> str:
    """嵌入 → 存入 aibrain_memories → 返回 ID"""
```

### Step 3：改造管线步骤

```python
# pipeline/steps/store/vector_store.py
from ..store import memory_store

def execute(ctx):
    result = memory_store(text, payload=full_meta)
    ctx.intermediate["mem0_ids"] = ...  # 字段名不变，下游无感
    ctx.metadata["_events"] = ...
```

```python
# pipeline/steps/search/vector_search.py
from ..store import memory_search

def execute(ctx):
    memories = memory_search(query, top_k=75, threshold=threshold)
    ctx.intermediate["semantic_results"] = memories
```

管线代码只看 `memory_store()` / `memory_search()`，将来切换后端只改这个接口文件。

### Step 4：清理（可选，任何时候）

```
停 mem0_server → 删 mem0_server/ 目录 → 删 mem0_adapter.py → 删 requirements 依赖
```

统一接口里去掉 `_search_legacy()` 调用即可。**可以第一步就做，也可以等确认老数据不再需要时再做。**

---

## 老数据兼容

现有 `mem0_memories`（416 条）保留只读，搜索时两个 collection 都查：

```
搜索 query
  ┬── aibrain_memories（新） → text + emotion + scene + ...
  └── mem0_memories（老）     → data 字段映射为 text
  └── 合并结果，按 score 排序，去重（id 重复优先保留新 collection）
```

下游 `event_recall` / `graph_recall` / `time_decay` 只看 `{id, text, score, source}`，新旧无区别。

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `memory/store.py` | 新建 | **统一接口层** — 管线唯一入口 |
| `memory/qdrant_store.py` | 新建 | 嵌入 + 存新 collection |
| `memory/qdrant_search.py` | 新建 | 嵌入 + 搜索 + payload 过滤 |
| `pipeline/steps/store/vector_store.py` | 修改 | `get_mem0_client()` → `memory_store()` |
| `pipeline/steps/search/vector_search.py` | 修改 | `get_mem0_client().search()` → `memory_search()` |
| `mem0_adapter.py` | 保留或删 | 不再被管线调用时可删，不删也不影响 |
| `mem0_server/` | 保留或删 | 停掉进程即可，代码可后续清理 |

**管线代码的改动只在一处**：`get_mem0_client()` → `memory_store()` / `memory_search()`。其他全部不变。

---

## 验证标准

- [ ] 新记忆通过 `memory_store()` 存入 `aibrain_memories`，payload 完整
- [ ] 搜索时新旧两个 collection 的结果都返回
- [ ] 老记忆的 `data` 字段被正确映射为 `text`，下游无感
- [ ] 停掉 mem0_server 后，新存储和搜索正常工作
- [ ] 统一接口层可独立测试：`memory_store()` / `memory_search()` 不依赖管线

---

## 补充说明

### `_merge_results` 合并规则

```python
def _merge_results(results):
    """合并新旧搜索结果，按 score 降序，id 重复保高分"""
    seen = {}
    for r in results:
        rid = r["id"]
        if rid not in seen or r["score"] > seen[rid]["score"]:
            seen[rid] = r
    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)
```

### 不影响的部分（无需改动）

| 模块 | 原因 |
|------|------|
| `core.py` 的 `list_memories()` | 直接调 `get_mem0_client()`，保留现状 |
| `core.py` 的 `delete_memory()` | 同上，删 mem0 时切换到新 collection |
| `mem0_adapter.py` | 保留不动，不再被管线调用后自然废弃 |
| 所有下游 pipeline 步骤 | 只看 `{id, text, score, source}`，新旧无区别 |
