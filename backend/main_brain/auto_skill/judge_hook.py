"""Judge 集成钩子 — 读取 SKILL.md 内容供 Judge 注入

在 judge.py 的 procedure_matches 注入逻辑中调用。

性能：load_skill_md 在单次目录扫描中同时完成查找和读取，避免双重 I/O。
每次调用扫描整个目录，在文件数 < 50 时（预期 5-20）延迟可忽略。
如未来文件数增长，可改为 sync_all 时构建内存索引。
"""

import glob
import logging
import os
from typing import Optional

from main_brain.auto_skill.deployer import SKILLS_STORE

logger = logging.getLogger("main_brain.auto_skill.judge_hook")


def load_skill_md(template_id: str) -> Optional[str]:
    """根据 template_id 加载对应的 SKILL.md 全文。

    单次扫描目录即可完成查找和读取，无双重 I/O。

    Args:
        template_id: 模板 ID。

    Returns:
        SKILL.md 全文，或 None（未部署/读取失败）。
    """
    # 扫描目录，读 frontmatter 匹配 template_id
    store_dir = SKILLS_STORE
    if not os.path.isdir(store_dir):
        return None

    for fpath in glob.glob(os.path.join(store_dir, "*.md")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # 只解析前几行 frontmatter 匹配 template_id
            if _frontmatter_has_id(content, template_id):
                return content
        except Exception as e:
            logger.debug("[auto_skill.judge_hook] skip unreadable %s: %s", fpath, e)
            continue

    return None


def _frontmatter_has_id(content: str, template_id: str) -> bool:
    """快速检查 frontmatter 中是否包含指定 template_id。

    只扫描 frontmatter 区域（第一个 --- 到第二个 --- 之间），不解析整个文件。
    """
    end = content.find("---", 3)  # 跳过开头的 ---
    if end == -1:
        return False
    front = content[3:end]
    return f"template_id: {template_id}" in front


def format_skills_for_prompt(matches: list[dict]) -> str:
    """将 procedure_matches 转换为带 SKILL.md 内容的 prompt 片段。

    每个匹配最多注入 1 个完整 SKILL.md，取前 2 个匹配。
    若无对应的 SKILL.md，fallback 回原来的统计摘要。

    Args:
        matches: procedure_matches 列表，每个包含 template_id。

    Returns:
        注入 prompt 的文本块（空字符串表示无匹配）。
    """
    if not matches:
        return ""

    skill_texts = []
    fallback_texts = []

    for m in matches[:2]:
        tid = m.get("template_id", "") if isinstance(m, dict) else getattr(m, "template_id", "")
        if not tid:
            continue

        skill_md = load_skill_md(tid)
        if skill_md:
            skill_texts.append(skill_md)
        else:
            # fallback: 输出匹配的统计摘要
            score = m.get("score", 0) if isinstance(m, dict) else getattr(m, "score", 0)
            reason = m.get("reason", "") if isinstance(m, dict) else getattr(m, "reason", "")
            fallback_texts.append(f"- 模板 {tid[:12]} (匹配度={score:.2f}) {reason}")

    if skill_texts:
        return "\n\n【匹配的经验技能】\n" + "\n---\n".join(skill_texts)
    if fallback_texts:
        return "\n匹配的程序记忆（无完整 SKILL.md）：\n" + "\n".join(fallback_texts)
    return ""
