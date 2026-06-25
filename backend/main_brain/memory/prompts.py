"""
事件记忆召回 - LLM Prompt 常量
用于事件提取、链推断、查询匹配
"""

EVENT_EXTRACT_PROMPT = """你是一个事件分析助手。从记忆文本中判断是否包含"事件"，如果有则提取为结构化事件。

事件定义：一个或多个人/角色发生了可叙述的动作或状态变化，包含主语+动作。
以下属于事件：
- "志远帮我升级了记忆系统" → 事件（主语志远 + 动作升级）
- "我们讨论了项目架构选择" → 事件（主语我们 + 动作讨论）
- "猫猫承诺会好好活着" → 事件（主语猫猫 + 动作承诺）
- "今天心情不好" → 事件（状态变化）

以下不属于事件（属于概念/事实）：
- "Python的GIL限制了多线程性能" → 概念
- "Unity光照衰减原理" → 概念
- "BGE-M3是1024维嵌入模型" → 事实

规则：
1. 每条记忆最多提取1个事件（取最显著的）
2. subject 和 action 尽量简短（2-8字）
3. summary 是完整的一句话概括
4. emotion 默认 neutral，只在有明显情感时才标注
5. importance 根据事件对当事人的影响程度评估（0-1）
6. is_first_occurrence 只在"首次见面/第一次做某事"时为 true

输出格式（严格遵守JSON，不要输出其他内容）：
{"type": "event", "event": {"subject": "主语", "action": "核心动作", "object": "对象或null", "context": "场景或null", "time_expr": "时间表达或null", "summary": "一句话概括", "emotion": "positive/negative/neutral/shock/warm/sad/excited", "emotion_intensity": 0.5, "importance": 0.5, "cause_hint": "可能原因关键词或null", "is_first_occurrence": false}}

如果无事件（概念/事实/知识），输出：
{"type": "concept", "event": null}"""


CHAIN_INFER_PROMPT = """你是一个事件关系分析助手。根据给定的事件列表，推断事件之间的因果和时序关系。

可选关系类型：
- cause_of: A 是 B 的原因（A导致B发生）
- effect_of: A 是 B 的结果（B导致A发生）
- next_in_sequence: A 之后发生了 B（时间先后，无明确因果）

规则：
1. 只推断有明确依据的关系，不确定就不要推断
2. confidence 为 0-1 之间的浮点数，低于 0.6 的不要输出
3. 最多输出 5 条关系
4. source_idx 和 target_idx 是事件列表中的索引号（从0开始）

输出格式（严格遵守JSON数组，不要输出其他内容）：
[{"source_idx": 0, "target_idx": 1, "relation_type": "cause_of", "confidence": 0.8}]

如果没有明确关系，输出空数组：[]"""


EVENT_MATCH_PROMPT = """你是一个事件检索助手。根据用户的搜索查询，从事件列表中找出相关的事件。

规则：
1. 按相关度排序，最相关的排在前面
2. 最多返回 10 个匹配
3. 宁可漏掉也不要误判（精确优于召回）
4. 同时匹配事件的 subject、action、object、summary 字段
5. 索引从 0 开始

输出格式（严格遵守JSON，不要输出其他内容）：
{"matched_indices": [0, 3, 5]}

如果没有匹配，输出：
{"matched_indices": []}"""
