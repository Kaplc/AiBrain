"""
skill_tools — Skill 加载工具

让 LLM 可以在对话中列出可用技能并加载技能内容。
加载的技能存入共享状态（不进 tool result），由 skills_inject section
在下一轮对话时注入 system prompt。

遵循 plan_tools.py / memory_tools.py 的代码模式。
"""
import logging
import os

from .registry import ToolDef

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, ".aibrain", "skills")

# 当前加载的技能（全局共享，不进 tool result）
_loaded_skill: dict | None = None  # {"name": str, "content": str}


def get_loaded_skill() -> dict | None:
    """返回当前加载的技能，供 skills_inject section 读取"""
    return _loaded_skill


def set_loaded_skill(name: str, content: str) -> None:
    """设置当前加载的技能（只保留一个）"""
    global _loaded_skill
    _loaded_skill = {"name": name, "content": content}


def clear_loaded_skill() -> None:
    """清除已加载的技能"""
    global _loaded_skill
    _loaded_skill = None


def _vp(subpath: str) -> str | None:
    """验证路径，返回完整路径或 None（防止路径穿越）"""
    full = os.path.normpath(os.path.join(_SKILLS_DIR, subpath))
    real = os.path.realpath(full)
    skills_real = os.path.realpath(_SKILLS_DIR)
    return real if real.startswith(skills_real) else None


def _list_skills() -> str:
    """扫描 .aibrain/skills/，读取每个 SKILL.md 的 frontmatter，返回格式化列表"""
    if not os.path.isdir(_SKILLS_DIR):
        return "可用技能（共 0 个）：\n  （技能目录不存在）"

    import yaml

    skills = []
    try:
        entries = sorted(os.listdir(_SKILLS_DIR))
    except OSError as e:
        return f"读取技能目录失败: {e}"

    for name in entries:
        skill_dir = os.path.join(_SKILLS_DIR, name)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isdir(skill_dir) or not os.path.isfile(skill_md):
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
        except Exception as e:
            logger.debug(f"[skill] frontmatter parse failed for {name}: {e}")
            # 解析失败时使用目录名作为技能名，描述置空
        skills.append((name, desc[:120] if desc else ""))

    if not skills:
        return "可用技能（共 0 个）：\n  （未找到技能）"

    lines = [f"可用技能（共 {len(skills)} 个）："]
    for sname, sdesc in skills:
        if sdesc:
            lines.append(f"  {sname} - {sdesc}")
        else:
            lines.append(f"  {sname}")
    lines.append("使用 skill_load 并指定 name 加载技能完整内容")
    return "\n".join(lines)


def _load_skill(name: str) -> str:
    """按名称加载一个技能的 SKILL.md 完整内容，存入共享状态

    Args:
        name: 技能名称（目录名）

    Returns:
        简短确认（内容由 skills_inject section 注入 system prompt）
    """
    if not name or not name.strip():
        return "需要指定技能名称（name 参数）"

    # 路径安全校验
    full = _vp(name)
    if full is None:
        return "错误：不允许访问技能目录以外的路径"
    skill_md = os.path.join(full, "SKILL.md")

    if not os.path.isfile(skill_md):
        return f"未找到技能: {name}"

    try:
        with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return f"读取技能文件失败: {e}"

    if len(content) > 20000:
        content = content[:20000] + "\n\n... (技能内容过长，仅显示前 20000 字符)"

    set_loaded_skill(name, content)
    logger.info(f"[skill] loaded: {name} ({len(content)} chars)")
    return f"已加载技能: {name}，内容已注入系统提示词"


def _skill_fn(action: str = "", name: str = "") -> str:
    """Skill 工具主函数

    Args:
        action: "list" 列出所有技能，"load" 加载指定技能
        name: action=load 时必填，技能名称

    Returns:
        格式化结果文本
    """
    if not action:
        return "需要指定 action 参数（list/load）"

    if action == "list":
        return _list_skills()

    if action == "load":
        return _load_skill(name)

    return f"未知操作: {action}（支持: list/load）"


SKILL_TOOL = ToolDef(
    name="skill",
    description="List available skills or load a skill's content by name. Skills are knowledge/task guides that help the AI perform specific tasks.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "load"],
                "description": "list=列出所有可用技能, load=按名称加载技能完整内容",
            },
            "name": {
                "type": "string",
                "description": "技能名称（action=load 时必填）",
            },
        },
        "required": ["action"],
    },
    fn=_skill_fn,
)


def register_skill_tools():
    """在 app.py 启动时调用，注册 skill 工具"""
    from .registry import get_tool_registry
    reg = get_tool_registry()
    reg.register(SKILL_TOOL)
