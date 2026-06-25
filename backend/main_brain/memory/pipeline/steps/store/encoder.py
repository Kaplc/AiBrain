"""
Encoder Step - 情景记忆编码（infer）
在 vector_store 之前运行，用一次 LLM 调用提取完整情景结构：
  display_text / episodic{what,why,result,lesson} / concepts / affect / importance
并拼接 embedding_text（供向量库索引整段情景，而非仅标题）。
全部写入 ctx.metadata["memory_meta"]，由 vector_store 自动并入 Qdrant payload。

所有新记忆都走情景格式（infer=True 时）。失败降级 SAFE_DEFAULTS，绝不阻塞存储。
"""
import logging

logger = logging.getLogger('memory.pipeline')

# 解析/调用失败时的兜底情景
SAFE_DEFAULTS = {
    "display_text": "",
    "episodic": {"what": "", "why": "", "result": "", "lesson": []},
    "nodes": [],
    "affect": {"intensity": 0.0},
    "importance": 0.3,
}

ALLOWED_NODE_TYPES = {"person", "concept", "emotion", "goal"}

ENCODER_PROMPT = """你是记忆编码助手。给定一条记忆文本，提取完整的情景结构，输出严格的 JSON。

【输出维度】
1. display_text: 一句话标题，概括这次经历（给人看，10-20字）
2. episodic:
   - what: 发生了什么（一句话）
   - why: 为什么发生/触发原因（文本无法推断则为空字符串 ""）
   - result: 结果如何（一句话）
   - lesson: 学到了什么/经验（数组，0-3 条，每条≤30字，无则空数组 []）
3. nodes: 核心语义节点（2-5 个），每个包含 name 和 type。
   type 取值（只选一个）：
   - person: 人物、参与者
   - concept: 技术、框架、概念、知识
   - emotion: 情绪、感受（成就感、挫败、温暖）
   - goal: 目标、意图、方向
4. affect: 情感分布。给出文本中体现的情感维度（每个 0-1，不必全填，有才给）+ intensity（情感烈度 -3.0~3.0，0 为中性）
   常见维度：warmth(温暖)/joy(喜悦)/gratitude(感激)/curiosity(好奇)/frustration(挫败)/sadness(难过)/pride(自豪)
5. importance: 这条记忆的重要性 0.0-1.0（里程碑/重大事件高分，日常低分）

【规则】
- 只输出一个 JSON 对象，禁止解释文字、禁止 markdown 代码块
- display_text / episodic / nodes / affect / importance 五个字段不可缺失
- nodes 至少包含 1 个节点，name 2-10 字
- affect 至少包含 intensity
- lesson 可为空数组

【输出格式】
{"display_text":"理解entity_relations工作原理","episodic":{"what":"志远解释了entity_relations如何工作","why":"此前无法理解网状记忆实现","result":"理解了关系激活机制","lesson":["entity_relations的价值在于激活关系","边被遍历时才产生意义"]},"nodes":[{"name":"志远","type":"person"},{"name":"entity_relations","type":"concept"},{"name":"成就感","type":"emotion"},{"name":"AiBrain","type":"goal"}],"affect":{"warmth":0.8,"gratitude":0.7,"intensity":2.0},"importance":0.85}"""


def _clamp_float(v, lo, hi, default):
    """安全转 float 并钳制到 [lo, hi]"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _normalize(obj: dict, fallback_text: str) -> dict:
    """校验并规范化 LLM 返回的情景对象，任何字段异常都用 SAFE_DEFAULTS 兜底"""
    if not isinstance(obj, dict):
        return _defaults_with_text(fallback_text)

    # display_text
    display = obj.get("display_text")
    if not isinstance(display, str) or not display.strip():
        display = fallback_text[:30]

    # episodic
    raw_epi = obj.get("episodic") or {}
    if not isinstance(raw_epi, dict):
        raw_epi = {}
    def _str(v):
        return v.strip() if isinstance(v, str) else ""
    what = _str(raw_epi.get("what"))
    why = _str(raw_epi.get("why"))
    result = _str(raw_epi.get("result"))
    raw_lesson = raw_epi.get("lesson") or []
    if not isinstance(raw_lesson, list):
        raw_lesson = []
    lesson = [_str(x)[:30] for x in raw_lesson if isinstance(x, str) and x.strip()][:3]

    # nodes
    raw_nodes = obj.get("nodes") or []
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    nodes = []
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name", "")).strip()
        typ = str(n.get("type", "")).strip()
        if len(name) < 2 or len(name) > 10:
            continue
        if typ not in ALLOWED_NODE_TYPES:
            typ = "concept"
        nodes.append({"name": name, "type": typ})

    # affect
    raw_affect = obj.get("affect") or {}
    if not isinstance(raw_affect, dict):
        raw_affect = {}
    affect = {}
    for k, v in raw_affect.items():
        if k == "intensity":
            affect["intensity"] = round(_clamp_float(v, -3.0, 3.0, 0.0), 3)
        elif isinstance(k, str) and k.replace("_", "").isalpha():
            affect[k] = round(_clamp_float(v, 0.0, 1.0, 0.0), 3)
    affect.setdefault("intensity", 0.0)

    # importance
    importance = round(_clamp_float(obj.get("importance", 0.3), 0.0, 1.0, 0.3), 3)

    return {
        "display_text": display,
        "episodic": {"what": what, "why": why, "result": result, "lesson": lesson},
        "nodes": nodes,
        "affect": affect,
        "importance": importance,
    }


def _defaults_with_text(text: str) -> dict:
    """兜底情景：display_text 用原文截断，其余空"""
    d = {
        "display_text": text[:30] if text else "",
        "episodic": dict(SAFE_DEFAULTS["episodic"]),
        "nodes": [],
        "affect": {"intensity": 0.0},
        "importance": 0.3,
    }
    return d


def _build_embedding_text(display: str, epi: dict) -> str:
    """拼接情景为嵌入源文本：display + what + why + result + lesson"""
    parts = [display] if display else []
    for key in ("what", "why", "result"):
        v = epi.get(key, "")
        if v:
            parts.append(v)
    for lesson in epi.get("lesson", []):
        if lesson:
            parts.append(lesson)
    return "\n".join(parts) if parts else (display or "")


def _read_life_state_context() -> str:
    """读取内部状态，转成自然语言文本给 LLM 参考。读取失败返回空字符串。"""
    try:
        from main_brain.adapters.state import get_state_adapter
        life = get_state_adapter().read_life_state()
        mood = life.get("mood", {})
        if isinstance(mood, str):
            mood_label = mood
        elif isinstance(mood, dict):
            mood_label = mood.get("label", "neutral")
        else:
            mood_label = "neutral"
        energy = float(life.get("energy", 0.6))
        focus = str(life.get("current_focus", ""))[:40]
        activity = str(life.get("current_activity", ""))[:30]

        from main_brain.state import get_state
        internal = get_state().snapshot()
        drives = internal.get("drives", {}) or {}

        parts = ["【记录这条记忆时我的状态】"]
        # mood 转自然语言
        mood_texts = {
            "neutral": "心情平静",
            "curious": "充满好奇",
            "happy": "心情愉悦",
            "excited": "有些兴奋",
            "tired": "有点疲惫",
            "sad": "情绪低落",
            "anxious": "有些不安",
            "grateful": "充满感激",
        }
        mood_desc = mood_texts.get(mood_label, mood_label)
        parts.append(mood_desc)

        # energy 转中文
        if energy >= 0.8:
            parts.append("精力充沛")
        elif energy >= 0.5:
            parts.append("精力正常")
        elif energy >= 0.3:
            parts.append("精力一般")
        else:
            parts.append("有些疲惫")

        # current_activity 转自然语言
        activity_texts = {
            "wait": "",
            "proactive_contact": "正在主动联系",
            "prepare_expression": "正在准备表达",
            "reflect": "正在反思",
            "chat": "正在聊天",
            "idle": "",
        }
        act_desc = activity_texts.get(activity, f"正在{activity}" if activity else "")
        if act_desc:
            parts.append(act_desc)

        if focus:
            parts.append(f"正在关注：{focus}")

        # drives 转自然语言
        drive_names = {
            "curiosity": "求知欲",
            "companionship": "陪伴欲",
            "self_expression": "表达欲",
            "completion": "完成欲",
        }
        strong_drives = [drive_names.get(k, k) for k, v in drives.items() if isinstance(v, (int, float)) and v >= 0.7]
        if strong_drives:
            parts.append(f"内心驱动力：{'、'.join(strong_drives)}强烈")

        return "，".join(parts) + "。"
    except Exception as e:
        logger.debug(f"[encoder] read life-state failed: {e}")
        return ""


def execute(ctx) -> None:
    """执行 Encoder 步骤：LLM 提取情景结构，写入 memory_meta

    Args:
        ctx: PipelineContext
            input_data: str (记忆文本，vector_store 之前的原文)
            metadata: {"infer": bool, ...}
    """
    text = ctx.input_data
    if not text or not str(text).strip():
        logger.info("[step:encoder] empty text, skip")
        return

    from main_brain.memory.llm import call_llm
    from main_brain.narrative.utils import parse_json

    # 读取内部状态作为 LLM 上下文
    state_context = _read_life_state_context()
    user_prompt = f"记忆文本：{text}"
    if state_context:
        user_prompt = f"{state_context}\n\n{user_prompt}"

    try:
        logger.info(f"[step:encoder] encoding | text={str(text)[:60]!r}")
        obj = None
        for attempt in range(1, 6):
            prompt = ENCODER_PROMPT if attempt == 1 else ENCODER_PROMPT + "\n注意：只输出严格的 JSON，不要多余文字。"
            raw = call_llm(prompt, user_prompt, timeout=30)
            obj = parse_json(raw)
            if obj is not None:
                break
            logger.warning(f"[step:encoder] parse_json failed (attempt {attempt}/5) | raw={str(raw)[:120]!r}")

        if obj is None:
            logger.warning("[step:encoder] all 5 attempts failed, using SAFE_DEFAULTS")
            encoded = _defaults_with_text(str(text))
        else:
            encoded = _normalize(obj, str(text))
    except Exception as e:
        logger.warning(f"[step:encoder] LLM call failed, using SAFE_DEFAULTS: {e}")
        encoded = _defaults_with_text(str(text))

    # 节点名称向量去重：与 aibrain_nodes 集合语义比对，避免 LLM 同一概念不同名
    if encoded.get("nodes"):
        from modules.qdrant.store import dedup_node_name
        try:
            deduped = []
            for nd in encoded["nodes"]:
                orig = nd["name"]
                nd["name"] = dedup_node_name(orig, nd["type"])
                deduped.append(nd)
            # 去重后合并同名节点（type 冲突时保留更高权重的）
            _TYPE_RANK = {"person": 4, "goal": 3, "concept": 2, "emotion": 1}
            seen = {}
            for nd in deduped:
                key = nd["name"]
                if key in seen and _TYPE_RANK.get(nd["type"], 0) <= _TYPE_RANK.get(seen[key]["type"], 0):
                    continue
                seen[key] = nd
            encoded["nodes"] = list(seen.values())
        except Exception as e:
            logger.warning(f"[encoder:node] node dedup failed (non-fatal): {e}")

    # 拼接 embedding_text（向量库索引整段情景）
    embedding_text = _build_embedding_text(encoded["display_text"], encoded["episodic"])

    # 写入 memory_meta，由 vector_store 自动并入 payload
    mem_meta = ctx.metadata.get("memory_meta") or {}
    ctx.metadata["memory_meta"] = mem_meta
    mem_meta["display_text"] = encoded["display_text"]
    mem_meta["embedding_text"] = embedding_text
    mem_meta["episodic"] = encoded["episodic"]
    mem_meta["nodes"] = encoded["nodes"]
    mem_meta["affect"] = encoded["affect"]
    mem_meta["importance"] = encoded["importance"]

    logger.info(
        f"[step:encoder] DONE | display={encoded['display_text'][:20]!r} "
        f"importance={encoded['importance']} intensity={encoded['affect'].get('intensity')} "
        f"nodes={len(encoded['nodes'])} lessons={len(encoded['episodic']['lesson'])}"
    )


def _make_step():
    """创建 Encoder StepDef"""
    from ...context import StepDef
    return StepDef(
        name="encoder",
        description="情景记忆编码（标题/情景/概念/情感/重要性）",
        execute=execute,
        enabled=True,
        required=False,
        pipeline="store",
        timeout=35.0,
    )
