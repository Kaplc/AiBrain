"""技能注入 — 已加载的技能注入 system prompt，未加载时显示可用技能列表"""
import logging
import os
import yaml

from ..context import PromptContext

logger = logging.getLogger('chat.pipeline')

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, ".aibrain", "skills")


def _scan_skills() -> list[dict]:
    """扫描 .aibrain/skills/，返回 [{name, description}]"""
    if not os.path.isdir(_SKILLS_DIR):
        return []
    skills = []
    try:
        entries = sorted(os.listdir(_SKILLS_DIR))
    except OSError:
        return []
    for name in entries:
        skill_md = os.path.join(_SKILLS_DIR, name, "SKILL.md")
        if not os.path.isdir(os.path.join(_SKILLS_DIR, name)) or not os.path.isfile(skill_md):
            continue
        desc = ""
        try:
            with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read(4096)
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    fm = yaml.safe_load(raw[3:end])
                    if isinstance(fm, dict):
                        desc = (fm.get("description") or "").strip()
        except Exception:
            pass
        skills.append({"name": name, "description": desc[:200] if desc else ""})
    return skills


def execute(ctx: PromptContext) -> None:
    try:
        # 1. 已加载的技能 → 单独开一个【当前技能】标签
        from modules.LLM.tools.skill_tools import get_loaded_skill
        loaded = get_loaded_skill()
        if loaded:
            name = loaded.get("name", "")
            content = loaded.get("content", "")
            if content:
                ctx.add_block(
                    "skills_loaded",
                    f"技能名称：{name}\n\n{content}",
                    title="当前技能",
                )

        # 2. 始终显示可用技能列表
        skills = _scan_skills()
        if skills:
            lines = [f"  {s['name']}" + (f" - {s['description']}" if s['description'] else "") for s in skills]
            lines.append("使用 skill load 可加载技能完整内容")
            ctx.add_block("skills_available", "\n".join(lines), title="可用技能")
    except Exception:
        pass


def _make_step():
    from .. import SectionDef
    return SectionDef(
        name="skills_inject",
        description="技能注入（已加载则进 system prompt，否则显示列表）",
        execute=execute,
        enabled=True,
        required=False,
    )
