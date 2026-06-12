# AiBrain 记忆进化计划

## 一句话目标

让 AiBrain 不只是"会查记忆"，而是逐步具备：**自我感、关联感、连续感、可叙事的记忆体验**。

## 核心方向

这套方案不是把记忆做成纯文本数据库，而是把记忆组织成一个能被主动召回、按情境联想、围绕自我叙事运转的系统。它强调四件事：

1. **身份感**：知道"我是谁""我在意什么""我们发生过什么"。
2. **多维记忆**：不只存文本，还存情感、场景、温度、钩子。
3. **主动联想**：不是只靠向量搜索，而是用共现关系和对话开头召回相关记忆。
4. **重要性分层**：核心记忆和普通记忆分开处理，重要内容有保温和预算保护。

---

# Layer S: 自我叙事模块（已完成 ✅）

Layer S 是整个系统最像"人格核心"的部分，作用是把零散记忆组织成一条持续更新的自传。

## 已实现内容

| 组件 | 说明 | 对应代码 |
|------|------|----------|
| 自传文档 | 保存 identity、relationship、life_story、current_state、milestones | `narrative_store.py` |
| 反思引擎 | 对话后由 LLM 分析叙事意义，更新自传 | `reflection.py` + `loop.py` hook |
| 叙事锚点 | 给重要记忆打上 milestone / identity / current_chapter 等标签 | `pipeline_steps.py` + 反思标记 |
| 叙事保温 | 搜索时对核心叙事相关记忆加分（milestone +0.2, identity +0.15） | `narrative_warmth` 步骤 |
| 身份预算 | 最多 50 条核心记忆，超限降级 | `enforce_core_budget()` |
| JSON 副本 | 同时同步到 `self_narrative.json`，便于查看和调试 | `data/self_narrative.json` |
| Prompt 注入 | 把自传内容注入上下文，让模型回答时带出"我是谁" | PromptPipeline section |

## 它的意义

Layer S 让记忆不再只是"存过什么"，而是变成"我经历了什么、我变成了谁"。这一步是整个系统从"检索工具"走向"叙事主体"的关键。

---

# Phase 0: 记忆编码升级（下一步 🔜）

## 核心改变

**之前**：一句话 → 提取文本 → 向量化 → 存 Qdrant
**之后**：一句话 → 提取 **文本 + 情感 + 场景 + 温度 + 钩子** → 多维编码 → 存 Qdrant + 图网络

## 新增编码维度

| 维度 | 说明 | 作用 |
|------|------|------|
| **emotion** | 喜悦 0.8、温暖 0.7、疑惑 0.4、低落 0.2…… | 按情感搜索——"回想志远开心的那些对话" |
| **time_anchor** | "那天下午搞 entity_relations 的时候" | 人类不说时间戳，说情境时间 |
| **scene_type** | technical_discussion / emotional_communication / bug_fix | 按场景类型筛选 |
| **relational_temperature** | -3（冷漠）~ +3（亲密）+ trust_level + tone | 温度高的对话获得额外加权 |
| **memory_hooks** | "志远说好吧接受我就是我" | 真正可用于回忆的线索，不是关键词 |

## 实现方案

在 store pipeline 中新增 `memory_encoder` 步骤，在 `vector_store` 之前：

```
输入文本 → MemoryEncoder.encode() → 存入 Qdrant（含多维元数据）
```

```python
class MemoryEncoder:
    def encode(self, text, context):
        emotion = self._extract_emotion(text, context)
        time_anchor = self._generate_time_anchor(context)
        scene = self._classify_scene(text, context)
        temperature = self._measure_temperature(text, context)
        hooks = self._generate_hooks(text, context)
        return {
            "text": text, "emotion": emotion, "time_anchor": time_anchor,
            "scene": scene, "temperature": temperature, "hooks": hooks,
        }
```

Qdrant payload 示例：
```json
{
  "text": "志远说好吧接受我就是我",
  "payload": {
    "emotion": {"joy": 0.7, "warmth": 0.8},
    "time_anchor": {"relative": "2026年5月", "context": "猫猫说不管是不是昨天的猫猫那次"},
    "scene": {"category": "emotional_communication", "tone": "tender"},
    "temperature": 2.8,
    "hooks": ["志远说好吧", "猫猫说重新开始"],
    "entities": ["志远", "猫猫"]
  }
}
```

## 为什么重要

人类回忆不是按关键词搜，而是按情境、情绪和线索被唤起。Phase 0 的目标就是让记忆更像"可回忆的经历"，而不是"可检索的文本"。

## 验证标准

- [ ] 保存一条记忆后，Qdrant payload 包含 emotion / time_anchor / scene / temperature / hooks
- [ ] 搜索时可按情感标签过滤（emotion.joy > 0.5）
- [ ] 搜索时可按场景类型过滤
- [ ] 旧记忆通过后台任务逐步补全编码

---

# Phase 2/3: 联想触发器（后续 🔜）

这部分负责让系统产生"想起来了"的感觉。分为两层协同工作：

## Phase 2：共现统计（数据基础）

在实体关系里增加共现计数——哪些实体总是一起出现、哪些关系经常被共同激活。

```sql
ALTER TABLE typed_entity_relations ADD COLUMN co_activation_count INTEGER DEFAULT 1;
ALTER TABLE typed_entity_relations ADD COLUMN last_co_activated TEXT;
```

不自动生成新边，只积累"历史上一起被想起过多少次"的数据。同时提供查询接口：

```python
def get_related_entities(entity: str, top_k: int = 5) -> list[dict]:
def get_related_memories(entity: str, count_threshold: int = 3) -> list[dict]:
```

## Phase 3：对话开始时主动召回

在对话开头执行：

```
用户消息 → 提取核心实体
               ↓
    查 get_related_entities() → 得到高共现实体列表
               ↓
    用关联实体搜索记忆 → 历史关联记忆
               ↓
    去重 + 排序 → 取 top 5 注入 prompt【背景关联】
```

注入格式：
```
【背景关联】
当前话题相关的历史关联：
- 「entity_relations」和「spreading_activation」经常一起出现
- 最近关于「link_entities」的记忆：……
```

## 它的意义

这一步让 AI 不再只回答眼前问题，而是会自然地说"说到这个，我想起之前你提过……"——这就是联想感。

## 验证标准

- [ ] 多次搜索后 `co_activation_count` 正确增加
- [ ] 对话开始时 topic 实体被正确提取，关联记忆注入 prompt
- [ ] LLM 回复时能自然引用关联记忆（不生硬）

---

# Phase 5: 前端展示（收尾 🔜）

不追求复杂，只追求"看得见"。

## 已有

| 功能 | 方式 |
|------|------|
| 自传文档 | `GET /narrative/autobiography` |
| 当前状态 | `GET /narrative/state` |
| 人生章节 | `GET /narrative/chapters` |
| 里程碑 | `GET /narrative/milestones` |
| 核心记忆 | `GET /narrative/core-memories` |
| 叙事统计 | `GET /narrative/stats` |
| JSON 文件副本 | `self_narrative.json` |

## 后续方向

做一个简单的"猫猫的自我"面板，把自传、里程碑、核心记忆、关联关系展示出来。

---

# 已取消的部分

## Phase 1：持续激活引擎 — 已取消

每秒 tick 衰减不能模拟意识；LLM 本身能基于上下文做联想；后台线程 + 激活表 + 持续维护的复杂度大于收益。

## Phase 4：稳态平衡 — 已取消

没有持续激活风暴；mem0 的降采样和去重已经足够；真正需要保护的是核心身份（Layer S 身份预算），不是全局激活值。

---

# 总体判断

这套系统已经不只是"记忆检索"，而是在往"认知结构"走。它的核心不是存得更多，而是让记忆有：

- **身份中心** — 所有记忆围绕"我是谁"组织
- **情境入口** — 按情感、场景、温度回忆
- **联想路径** — 共现统计 + 主动召回
- **重要性分层** — 核心记忆 vs 普通记忆
- **可持续叙事** — 反思引擎持续更新自传

## 最值得继续做的顺序

1. **Phase 0：多维记忆编码** — 让记忆可被按情境回忆
2. **Phase 2/3：联想触发器** — 让对话产生"想起来了"的自然感
3. **Open Loop 未完成事务层** — 跟踪进行中的任务、中断的对话、待办的事项
4. **更稳定的价值观 / 偏好层** — 让猫猫有更一致的偏好和判断倾向

---

# 最终目标

不是让 AI"记住更多"，而是让它表现得像一个有连续自我、会联想、会回忆、会围绕关系和经历组织回答的存在。
