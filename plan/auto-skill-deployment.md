# Plan: 程序记忆 → 自动技能部署 (Auto-Skill)

## TL;DR

`procedural_memory` 挖出高置信度行为模板 → 格式化为标准 SKILL.md → 写入 `main_brain/data/auto_skills/` → Judge 的 `procedure_matches` 直接加载注入 → LLM 决策时自然参考经验。不再生成 Python 代码，不碰 ToolRegistry。

**核心变化**：程序记忆的输出从"干巴巴的统计数字"变成"结构化的经验指令"，通过已有技能注入链路辅助 LLM 决策。失败自动撤回。

---

## 现有基础设施（无需重复造）

| 现有组件 | 作用 | 本次是否修改 |
|---------|------|------------|
| `procedural_memory/miner.py` | 从 brain_runs 挖掘行为模板 | ❌ 不变 |
| `procedural_memory/matcher.py` | 上下文匹配 → 返回 `procedure_matches` | ❌ 不变 |
| `judge.py` (L141-146) | 已读取 `procedure_matches` 并注入 prompt | ✅ 改为加载 SKILL.md 内容 |
| `skills_inject.py` | 从 `.aibrain/skills/` 注入技能到 system prompt | ❌ 不依赖此路径 |
| `skill_tools.py` | LLM 对话中手动 `skill load` | ❌ 不变 |

---

## 新方案：自动技能路径

### 数据流

```
procedural_memory/miner.py → 挖出模板（status=active, confidence≥0.6）
    │
    ▼
auto_skill/formatter.py ──→ 格式化为 SKILL.md
    │  YAML frontmatter + 步骤描述 + 触发条件 + 成功标准
    ▼
写入 backend/main_brain/data/auto_skills/<skill_name>/SKILL.md
    │
    ▼
judge.py 的 procedure_matches 改为直接读取对应 SKILL.md 全文
    │  （不再是干巴巴的统计）
    ▼
feedback 追踪执行结果 → 更新模板置信度
    │
    ▼
置信度降级 → 自动删除 SKILL.md（回滚）
```

### 生成的 SKILL.md 格式

```markdown
---
name: auto_reflect_after_chat
description: 聊天后自动反思并更新自我认知
source: procedural_memory
confidence: 0.85
trigger: reactive mode, after final_reply
risk: low
version: 1
---

# auto_reflect_after_chat

## 触发条件
- mode=reactive
- 上一步 action=final_reply
- 有至少 3 条新记忆

## 执行步骤
1. 调用 reflection 更新自我叙事
2. 检查是否有未解决的 open_loops
3. 如有，记入 working_set 供下次决策

## 成功标准
- 自我叙事中 belief/goal/interests 有更新
- 未决问题被推进或关闭

## 注意事项
- 不要在一次运行中重复触发
- 如果用户连续发消息，跳过
```

---

## 组件设计

### 1. 格式化器 (`auto_skill/formatter.py`)

输入 `ProcedureTemplate` → 输出 SKILL.md 文本（无需 LLM 调用，纯模板渲染）：

```python
def format_as_skill_md(template: ProcedureTemplate) -> str:
    """将模板渲染为 SKILL.md 格式"""
```

**规则**：
- name = `auto_` + 模板 activity
- source = `procedural_memory`
- 步骤直接来自 `template.steps`
- 触发条件来自 `template.trigger_signals`
- 成功标准来自 `template.success_criteria`

**无需 LLM**，模板填写即可。降低复杂度和失败点。

**文件**：`backend/main_brain/auto_skill/formatter.py`

### 2. 部署器 (`auto_skill/deployer.py`)

```python
_SKILLS_STORE = os.path.join(_BASE, "data", "auto_skills")

def deploy_skill(template: ProcedureTemplate) -> dict:
    """写入 SKILL.md → 返回路径"""
    
def undeploy_skill(skill_name: str) -> bool:
    """删除 SKILL.md → 撤回"""
    
def list_deployed() -> list[dict]:
    """列出已部署的自动技能"""
```

**文件**：`backend/main_brain/auto_skill/deployer.py`

### 3. Judge 集成

修改 `judge.py` 中 `procedure_matches` 的注入逻辑：

```python
# 现有（L141-146）：
matches = judge_view.get("procedure_matches") or []
if matches:
    prompt += "\n" + format_procedure_matches_for_prompt(matches)

# 改为：
matches = judge_view.get("procedure_matches") or []
if matches:
    skill_texts = []
    for m in matches[:2]:  # 最多注入 2 个
        skill_md = _load_auto_skill(m["template_id"])
        if skill_md:
            skill_texts.append(skill_md)
    if skill_texts:
        prompt += "\n\n【匹配的经验技能】\n" + "\n---\n".join(skill_texts)
    else:
        prompt += "\n" + format_procedure_matches_for_prompt(matches)  # fallback
```

**文件**：`backend/main_brain/auto_skill/judge_hook.py`（新增）+ `backend/main_brain/judge.py`（修改 L141-146）

### 4. 回滚器 (`auto_skill/rollback.py`)

与 `procedural_memory/feedback.py` 联动：

| 条件 | 动作 |
|------|------|
| 模板 confidence < 0.5 | 删除对应 SKILL.md |
| 模板 status → deprecated/archive | 删除对应 SKILL.md |
| 模板 source_example_ids 被清除 | 删除对应 SKILL.md |

**文件**：`backend/main_brain/auto_skill/rollback.py`

不需要 monitoring 阶段 — SKILL.md 只是文本注入，LLM 可以选择忽略，风险极低。

### 5. 公共 API (`auto_skill/__init__.py`)

```python
def sync_all() -> dict:
    """扫描所有 active 模板 → 部署/更新/撤回 SKILL.md → 返回统计"""
```

---

## 调度集成

在 `procedural_memory/scheduler.py` 的 `run_mining()` 末尾新增：

```python
def run_mining(window=50):
    # ... 现有采集+挖掘逻辑 ...
    # 新增：自动同步技能
    try:
        from main_brain.auto_skill import sync_all
        sync_all()
    except Exception:
        pass
```

---

## 涉及文件

| 文件 | 操作 |
|------|------|
| `backend/main_brain/auto_skill/__init__.py` | 新建 — 公共 API `sync_all()` |
| `backend/main_brain/auto_skill/formatter.py` | 新建 — 模板 → SKILL.md 渲染 |
| `backend/main_brain/auto_skill/deployer.py` | 新建 — 写入/删除/列出 SKILL.md |
| `backend/main_brain/auto_skill/rollback.py` | 新建 — 置信度下降时撤回 |
| `backend/main_brain/auto_skill/judge_hook.py` | 新建 — Judge 读取 SKILL.md 工具函数 |
| `backend/main_brain/data/auto_skills/` | 新建 — 自动技能存储目录 |
| `backend/main_brain/judge.py` | 修改 — L141-146 走 SKILL.md 注入 |
| `backend/main_brain/procedural_memory/scheduler.py` | 修改 — `run_mining()` 末尾调用 `sync_all()` |
| `backend/main_brain/procedural_memory/feedback.py` | 修改 — 置信度降级时触发 rollback |
| `backend/main_brain/procedural_memory/__init__.py` | 修改 — re-export auto_skill 符号 |

---

## 与现有系统的关系

```
手工 Skill (.aibrain/skills/)
    │  skills_inject → system prompt（LLM 对话可见）
    │
自动 Skill (main_brain/data/auto_skills/)
    │  procedure_matches → Judge prompt（Brain 决策可见）
    │
两者完全独立，互不干扰。
手工 Skill 由用户手动 `skill load` 管理；
自动 Skill 由程序记忆自动部署/撤回。
```

---

## 验证

1. `formatter.py` 测试：输入模拟 `ProcedureTemplate`，验证输出 SKILL.md 格式正确
2. `deployer.py` 测试：写入后文件存在 → 删除后文件消失
3. 端到端测试：`run_mining()` → 自动技能出现在 `data/auto_skills/` → Judge prompt 包含技能内容
4. `feedback` 触发 rollback：置信度降到 0.4 → 文件自动删除
