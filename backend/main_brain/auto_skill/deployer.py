"""Auto-Skill 部署器 — 写入/删除/列出 SKILL.md 文件

SKILL.md 保存在 backend/main_brain/data/auto_skills/ 下，
每个模板对应一个文件，文件名为 auto_{safe_name}_{template_id[:8]}.md。
"""

import glob
import logging
import os
from typing import Optional

from main_brain.procedural_memory.contracts import ProcedureTemplate

logger = logging.getLogger("main_brain.auto_skill.deployer")

# SKILL.md 存储根目录
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_STORE = os.path.join(_BASE_DIR, "data", "auto_skills")
_SKILLS_STORE = SKILLS_STORE  # 向下兼容


def _ensure_store() -> None:
    """确保存储目录存在。"""
    os.makedirs(_SKILLS_STORE, exist_ok=True)


def deploy_skill(template: ProcedureTemplate) -> dict:
    """将模板部署为 SKILL.md 文件。

    Args:
        template: 符合条件的程序记忆模板。

    Returns:
        {"ok": bool, "path": str, "name": str, "template_id": str}
    """
    from main_brain.auto_skill.formatter import format_as_skill_md, get_skill_filename

    try:
        _ensure_store()
        content = format_as_skill_md(template)
        filename = get_skill_filename(template)
        filepath = os.path.join(_SKILLS_STORE, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("[auto_skill.deployer] deployed %s -> %s", template.template_id, filename)
        return {
            "ok": True,
            "path": filepath,
            "name": f"auto_{template.name}",
            "template_id": template.template_id,
        }
    except Exception as e:
        logger.exception("[auto_skill.deployer] deploy failed: %s", e)
        return {"ok": False, "template_id": template.template_id, "reason": str(e)}


def undeploy_skill(skill_name: str) -> bool:
    """删除一个已部署的 SKILL.md。

    支持按文件名或模板名匹配。

    Args:
        skill_name: 技能名（如 "auto_reflect_after_chat"）或完整文件名。

    Returns:
        是否成功删除。
    """
    _ensure_store()
    # 先按精确文件名查找
    filepath = os.path.join(_SKILLS_STORE, skill_name)
    if not skill_name.endswith(".md"):
        filepath += ".md"

    if os.path.isfile(filepath):
        os.remove(filepath)
        logger.info("[auto_skill.deployer] undeployed %s", skill_name)
        return True

    # 按名称前缀匹配
    prefix = skill_name.replace(".md", "")
    pattern = os.path.join(_SKILLS_STORE, f"{prefix}*.md")
    matches = glob.glob(pattern)
    for match in matches:
        os.remove(match)
        logger.info("[auto_skill.deployer] undeployed %s", os.path.basename(match))
    if not matches:
        logger.debug("[auto_skill.deployer] undeploy skipped: %s not found", skill_name)
    return len(matches) > 0


def list_deployed() -> list[dict]:
    """列出所有已部署的自动技能。

    Returns:
        每个技能的定义摘要列表。
    """
    _ensure_store()
    skills = []
    for fpath in sorted(glob.glob(os.path.join(_SKILLS_STORE, "*.md"))):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            metadata = _parse_frontmatter(content)
            skills.append({
                "file": os.path.basename(fpath),
                "path": fpath,
                "name": metadata.get("name", ""),
                "description": metadata.get("description", ""),
                "confidence": metadata.get("confidence", 0),
                "risk": metadata.get("risk", "low"),
                "version": metadata.get("version", 1),
            })
        except Exception as e:
            logger.warning("[auto_skill.deployer] failed to read %s: %s", fpath, e)
    return skills


def get_skill_path(template_id: str) -> Optional[str]:
    """根据 template_id 查找已部署的 SKILL.md 路径。

    Args:
        template_id: 模板 ID。

    Returns:
        文件路径，或 None。
    """
    _ensure_store()
    # 扫码所有 SKILL.md，匹配 frontmatter 中的 template_id
    for fpath in glob.glob(os.path.join(_SKILLS_STORE, "*.md")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            meta = _parse_frontmatter(content)
            if meta.get("template_id") == template_id:
                return fpath
        except Exception:
            continue
    return None


def _parse_frontmatter(text: str) -> dict:
    """简易 YAML frontmatter 解析。"""
    import re
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            # 数值类型
            try:
                if "." in val:
                    val = float(val)
                else:
                    val = int(val)
            except ValueError:
                pass
            if val == "true":
                val = True
            elif val == "false":
                val = False
            result[key] = val
    return result
