"""自我叙事片段 — 注入猫猫的当前自我认知、心情、里程碑"""
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
        parts.append(f"和志远的对话次数：{conv_count}")

        # ── 里程碑（最近 3 条） ──
        milestones = bio.get("milestones", [])
        if milestones:
            parts.append("")
            parts.append("重要里程碑：")
            for m in milestones[-3:]:
                title = m.get("title", m.get("description", ""))
                if title:
                    parts.append(f"  - {title}")

        # ── 当前人生章节 ──
        chapters = bio.get("life_story", {}).get("chapters", [])
        chapter_idx = bio.get("life_story", {}).get("current_chapter_index", 0)
        if chapters and 0 <= chapter_idx < len(chapters):
            ch = chapters[chapter_idx]
            ch_title = ch.get("title", "")
            ch_summary = ch.get("summary", "")
            if ch_title:
                parts.append("")
                parts.append(f"当前人生章节：{ch_title}")
                if ch_summary:
                    parts.append(f"  章节概要：{ch_summary}")

        if len(parts) > 3:
            ctx.add_section("自我叙事", "\n".join(parts))

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
