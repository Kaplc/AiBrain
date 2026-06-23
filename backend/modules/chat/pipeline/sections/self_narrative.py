"""自我叙事片段 — 注入猫猫的心情、反思摘要、信念/兴趣/目标/未解问题/领悟"""
from ..context import PromptContext


def execute(ctx: PromptContext) -> None:
    """读取自传文档，将关键状态注入 system prompt"""
    try:
        from modules.brain.memory.self_narrative import get_self_narrative
        store = get_self_narrative()
        if store is None:
            return

        bio = store.get_autobiography()
        if not bio:
            return

        parts = []

        # ── 当前状态 ──
        state = bio.get("current_state", {})
        mood = state.get("mood", "neutral")
        thinking = state.get("thinking", "")
        conv_count = state.get("conversation_count", 0)

        mood_map = {
            "excited": "兴奋",
            "happy": "开心",
            "warm": "温暖",
            "sad": "难过",
            "neutral": "平静",
            "positive": "积极",
            "negative": "低落",
            "shock": "惊讶",
        }
        mood_cn = mood_map.get(mood, mood)
        parts.append(f"当前心情：{mood_cn}")
        if thinking:
            parts.append(f"最近在想：{thinking}")
        # 反思摘要（what_this_means）
        summary = state.get("last_reflection_summary", "")
        if summary:
            parts.append(f"上次反思：{summary}")
        # 情感影响
        emo = state.get("last_emotional_impact", "")
        if emo and emo != "neutral":
            emo_map = {"positive": "积极", "negative": "低落", "warm": "温暖",
                       "sad": "难过", "excited": "兴奋"}
            parts.append(f"情绪倾向：{emo_map.get(emo, emo)}")
        parts.append(f"和志远的对话次数：{conv_count}")

        # ── 认知状态 ──
        labels = {
            "beliefs": "我逐渐相信",
            "interests": "我在意的事",
            "goals": "我想实现的目标",
            "open_questions": "我还没想明白的",
            "recent_realizations": "我最近的领悟",
        }
        for field, label in labels.items():
            items = bio.get(field, [])
            if items:
                parts.append("")
                parts.append(f"{label}：")
                for item in items[-3:]:
                    parts.append(f"  · {item}")

        if len(parts) > 3:
            ctx.add_block("self_narrative", "\n".join(parts), title="自我叙事")

    except Exception:
        # 自我叙事不可用时不阻塞对话
        pass


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="self_narrative",
        description="自我叙事状态",
        execute=execute,
        enabled=True,
        required=False,
    )
