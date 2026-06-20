"""
LLM 调用封装 - 复用 mem0 配置，通过 OpenAI 兼容接口统一调用
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个记忆整理助手。你的任务是将多条语义相似的记忆合并为一条更精炼、更完整的描述。

规则：
1. 合并时保留所有关键信息，不遗漏重要细节
2. 去除重复表述，使文本更简洁
3. 保持原有时序信息（如日期、时间顺序）
4. 用中文输出
5. 如果记忆之间存在矛盾，保留最新的信息，并标注矛盾点
6. 自动判断记忆类型，从以下5类中选择：user/feedback/project/reference/ai
   - user: 用户个人信息、偏好、习惯、感受
   - feedback: 用户反馈、建议、意见、改进想法
   - project: 项目开发、代码、功能实现、技术任务
   - reference: 文档、链接、参考资料、学习笔记
   - ai: AI 自身的行为、偏好、记忆、经验总结

输出格式（严格遵守JSON）：
{"refined_text": "合并后的精炼文本", "category": "类型"}"""


RELATION_TYPES = ["causal", "similar", "partof", "temporal", "contradicts", "associated"]

RELATION_INFER_PROMPT = """你是一个实体关系分析助手。根据给定的记忆文本和其中出现的实体，推断实体之间的关系类型。

可选关系类型：
- causal: A 导致/引起 B
- similar: A 与 B 相似/同类
- partof: A 是 B 的一部分/属于 B
- temporal: A 与 B 有时间先后关系
- contradicts: A 与 B 矛盾/对立
- associated: A 与 B 有一般性关联（默认类型）

规则：
1. 只推断有明确依据的关系，不确定的用 "associated"
2. confidence 为 0-1 之间的浮点数，表示推断的可信度
3. 实体对顺序不重要（双向关系）

输出格式（严格遵守JSON数组）：
[{"from": "实体A", "to": "实体B", "relation_type": "关系类型", "confidence": 0.8}]"""

ENTITY_EXTRACT_PROMPT = """从文本中提取核心节点（1-5个），并判断记忆归属。

节点类型（必填，只选一个）：
- person: 人物、参与者
- concept: 技术、框架、概念、知识
- project: 项目、系统、工具
- emotion: 情绪、感受（激动、成就感、挫败、温暖）
- goal: 目标、意图、方向

归属分类（必填，只选一个）：
- 用户：用户个人的经历、偏好、计划、感受
- 自己：AI自身的行为、经验总结、决策
- 事实：客观知识、规则、定义、技术文档
- 经验：经验教训、最佳实践、踩坑记录

规则：
1. 最多提取5个节点，少了更好，没有可返回空数组
2. 只提取名词性节点，不提取形容词或状态描述
3. 不提取泛化词（如：一致性、维度、状态、生命周期、属性、标签、计数、写入、渲染、解析、进展、方面、事情、东西）
4. 不提取字段名/变量名（如：entities、stats、store、config）
5. 每个节点名 2-8个字，不要拆分复合词
6. emotion 类型只用于有明显情绪色彩的节点（如"成就感""挫败""温暖"）

输出格式（严格遵守JSON，不要其他内容）：
{"nodes": [{"name": "志远", "type": "person"}, {"name": "entity_relations", "type": "concept"}], "root": "用户"}"""


def _load_llm_config() -> dict:
    """从 llm.json 读取 LLM 配置（设置→LLM 页面配的）"""
    from core.settings import ConfigManager
    cfg = ConfigManager.get_instance().read_llm()
    return {
        "provider": cfg.get("provider", "openai"),
        "model": cfg.get("model", "gpt-4o-mini"),
        "api_key": cfg.get("api_key", ""),
        "base_url": cfg.get("base_url", ""),
    }


def _build_user_prompt(memories: list[dict]) -> str:
    """构建用户 prompt"""
    lines = [f"请合并以下 {len(memories)} 条相似记忆：", ""]
    for i, mem in enumerate(memories, 1):
        lines.append(f"[{i}] {mem['text']}")
    lines.append("")
    lines.append("请输出JSON格式的合并结果。")
    return "\n".join(lines)


def _parse_llm_response(raw: str) -> dict:
    """解析 LLM 返回的 JSON，支持容错提取"""
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取第一个 {...}
    m = re.search(r"\{[^{}]*\"refined_text\"[^{}]*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 降级：原始文本作为 refined_text
    logger.warning(f"[llm] JSON 解析失败，使用原始文本: {raw[:100]}")
    return {"refined_text": raw, "category": "reference"}


def call_llm(system_prompt: str, user_prompt: str, timeout: int = 30) -> str:
    """调用 LLM，返回原始文本响应"""
    cfg = _load_llm_config()
    provider = cfg["provider"]

    # 确定 base_url
    base_url = cfg.get("base_url", "")
    if not base_url:
        if provider == "ollama":
            base_url = "http://localhost:11434/v1"
        elif provider == "lmstudio":
            base_url = "http://localhost:1234/v1"

    from openai import OpenAI
    kwargs = {"api_key": cfg["api_key"] or "dummy"}
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)

    response = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=1024,
        timeout=timeout,
    )
    return response.choices[0].message.content.strip()


def refine_group(memories: list[dict]) -> dict:
    """对一组相似记忆调用 LLM 合并精炼

    Args:
        memories: [{"id": "...", "text": "..."}, ...]

    Returns:
        {"original_ids": [...], "original_texts": [...], "refined_text": "...", "category": "...", "refined": True/False}
    """
    original_ids = [m["id"] for m in memories]
    original_texts = [m["text"] for m in memories]

    try:
        user_prompt = _build_user_prompt(memories)
        raw = call_llm(SYSTEM_PROMPT, user_prompt)
        result = _parse_llm_response(raw)
        return {
            "original_ids": original_ids,
            "original_texts": original_texts,
            "refined_text": result.get("refined_text", raw),
            "category": result.get("category", "reference"),
            "refined": True,
        }
    except Exception as e:
        logger.warning(f"[llm] 精炼失败，降级拼接: {e}")
        # 降级：拼接所有原始文本
        fallback = " | ".join(original_texts)
        return {
            "original_ids": original_ids,
            "original_texts": original_texts,
            "refined_text": fallback,
            "category": "reference",
            "refined": False,
        }


def _parse_relation_response(raw: str) -> list[dict]:
    """Parse LLM response for relation inference"""
    # Try direct parse
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try extracting JSON array from code block
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first [...] in text
    m = re.search(r"\[.*?\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"[llm] relation JSON parse failed: {raw[:100]}")
    return []


def infer_relations(entities: list[str], memory_text: str) -> list[dict]:
    """Call LLM to infer relation types between entities

    Args:
        entities: list of entity names
        memory_text: the memory text providing context

    Returns:
        list of {"from": str, "to": str, "relation_type": str, "confidence": float}
    """
    if len(entities) < 2:
        return []

    entity_list = "\n".join(f"- {e}" for e in entities)
    user_prompt = f"""记忆文本：{memory_text}

出现的实体：
{entity_list}

请推断这些实体之间的关系，输出JSON数组。"""

    try:
        raw = call_llm(RELATION_INFER_PROMPT, user_prompt, timeout=15)
        relations = _parse_relation_response(raw)
        # Validate and filter
        valid = []
        entity_set = set(entities)
        for r in relations:
            if not isinstance(r, dict):
                continue
            fr = r.get("from", "")
            to = r.get("to", "")
            rel_type = r.get("relation_type", "associated")
            conf = r.get("confidence", 0.5)
            if fr in entity_set and to in entity_set and fr != to:
                valid.append({
                    "from": fr,
                    "to": to,
                    "relation_type": rel_type if rel_type in RELATION_TYPES else "associated",
                    "confidence": min(1.0, max(0.0, float(conf))),
                })
        return valid
    except Exception as e:
        logger.warning(f"[llm] infer_relations failed: {e}")
        return []


def _parse_extract_response(raw: str) -> dict | None:
    """解析 LLM 实体提取响应，返回 dict，失败返回 None

    新格式："nodes": [{"name": "...", "type": "person|concept|project|emotion|goal"}]
    旧格式（向后兼容）："entities": ["实体1", "实体2"]
    """
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        result = json.loads(m.group(0))
        if isinstance(result, dict):
            root = result.get("root", "用户")
            if root not in ("用户", "自己", "事实", "经验"):
                root = "用户"

            # 新格式：nodes
            raw_nodes = result.get("nodes", [])
            if raw_nodes and isinstance(raw_nodes, list):
                allowed_types = {"person", "concept", "project", "emotion", "goal"}
                nodes = []
                entities = []
                for n in raw_nodes:
                    if not isinstance(n, dict):
                        continue
                    name = str(n.get("name", "")).strip()
                    typ = str(n.get("type", "")).strip()
                    if len(name) < 2 or len(name) > 10:
                        continue
                    if typ not in allowed_types:
                        typ = "concept"
                    nodes.append({"name": name, "type": typ})
                    entities.append(name)
                entities = list(dict.fromkeys(entities))
                if nodes:
                    return {"nodes": nodes, "entities": entities, "root": root}

            # 旧格式回退：entities
            entities = result.get("entities", [])
            entities = list(dict.fromkeys(e for e in entities if isinstance(e, str) and 2 <= len(e) <= 10))
            if entities:
                return {"entities": entities, "root": root}
    # fallback: 纯数组
    m = re.search(r"\[.*?\]", raw, re.DOTALL)
    if m:
        result = json.loads(m.group(0))
        if isinstance(result, list):
            names = [e for e in result if isinstance(e, str) and 2 <= len(e) <= 10]
            return {"entities": list(dict.fromkeys(names)), "root": "用户"}
    return None


def extract_entities_llm(text: str, max_retries: int = 5) -> dict:
    """调用 LLM 提取实体名，JSON 解析失败自动重试"""
    if not text or not text.strip():
        return {"entities": [], "root": "用户"}
    for attempt in range(1, max_retries + 1):
        try:
            raw = call_llm(ENTITY_EXTRACT_PROMPT, f"文本：{text}", timeout=30)
            result = _parse_extract_response(raw)
            if result:
                return result
            logger.warning(f"[llm] extract_entities parse failed (attempt {attempt}/{max_retries}) | raw={raw[:100]}")
        except Exception as e:
            logger.warning(f"[llm] extract_entities call failed (attempt {attempt}/{max_retries}): {e}")
    logger.warning(f"[llm] extract_entities all {max_retries} attempts failed")
    return {"entities": [], "root": "用户"}


FILTER_RELATED_PROMPT = """你是一个记忆相关性判断助手。给定一个搜索 query 和一组候选记忆，选出最多10条最相关的记忆。

规则：
1. 相关 = 记忆内容和 query 的主题/人物/事件有直接联系
2. 按相关度从高到低排序，最相关的排在前面
3. 最多返回10条，不足10条就只返回有的
4. 宁可漏掉也不要误判不相关的记忆

输出格式（严格遵守JSON，不要其他内容）：
{"related": [3, 0, 7, 2, 5]}"""


def _parse_filter_response(raw: str, candidate_count: int) -> list[int]:
    """解析 LLM 过滤响应，返回相关记忆的编号列表"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, dict) and "related" in result:
                indices = result["related"]
                if isinstance(indices, list):
                    return [i for i in indices if isinstance(i, int) and 0 <= i < candidate_count]
        except json.JSONDecodeError:
            pass
    # fallback: 尝试从文本中提取数字
    numbers = re.findall(r'\b(\d+)\b', raw)
    return [int(n) for n in numbers if int(n) < candidate_count]


def filter_related_memories(query: str, candidates: list[dict], max_retries: int = 5) -> list[str]:
    """打包候选记忆，一次 LLM 调用返回相关记忆的 ID 列表。重试5次，失败降级返回空列表。

    Args:
        query: 搜索 query
        candidates: [{"id": "...", "text": "...", ...}, ...]

    Returns:
        相关记忆的 ID 列表
    """
    if not candidates:
        return []

    candidate_lines = "\n".join(
        f"{i}. {c['text'][:120]}"
        for i, c in enumerate(candidates)
    )
    user_prompt = f"Query: {query}\n\n候选记忆:\n{candidate_lines}\n\n请判断哪些记忆和 query 意图相关，返回相关记忆的编号列表。"

    for attempt in range(1, max_retries + 1):
        try:
            raw = call_llm(FILTER_RELATED_PROMPT, user_prompt, timeout=15)
            indices = _parse_filter_response(raw, len(candidates))
            if indices is not None:
                related_ids = [candidates[i]["id"] for i in indices if i < len(candidates)]
                logger.info(f"[llm:filter] query={query[:30]!r} | candidates={len(candidates)} | related={len(related_ids)} | attempt={attempt}")
                return related_ids
            logger.warning(f"[llm:filter] parse failed (attempt {attempt}/{max_retries}) | raw={raw[:100]}")
        except Exception as e:
            logger.warning(f"[llm:filter] call failed (attempt {attempt}/{max_retries}): {e}")

    logger.warning(f"[llm:filter] all {max_retries} attempts failed, returning empty")
    return []
