"""
记忆整理模块 - 按类型分类并结构化记忆
从 brain_mcp/_organizer.py 迁移至此
"""
import re
import logging
from datetime import datetime
from typing import Dict, List

from brain_mcp.embedding import encode_texts

logger = logging.getLogger(__name__)

TYPE_DESCRIPTIONS = {
    "user": "用户个人信息、偏好、习惯、感受",
    "feedback": "用户反馈、建议、意见、改进想法",
    "project": "项目开发、代码、功能实现、技术任务",
    "reference": "文档、链接、参考资料、学习笔记",
    "ai": "AI 自身的行为、偏好、记忆、经验总结"
}


def classify_memories(memories: List[Dict]) -> Dict[str, List[Dict]]:
    if not memories:
        return {t: [] for t in TYPE_DESCRIPTIONS}

    texts = [m["text"] for m in memories]
    text_vectors = encode_texts(texts)
    type_vectors = encode_texts(list(TYPE_DESCRIPTIONS.values()))

    categorized = {t: [] for t in TYPE_DESCRIPTIONS}
    for i, mem in enumerate(memories):
        text_vec = text_vectors[i]
        best_type = "reference"
        best_score = -1.0
        for j, (type_name, type_desc) in enumerate(TYPE_DESCRIPTIONS.items()):
            type_vec = type_vectors[j]
            score = sum(a * b for a, b in zip(text_vec, type_vec))
            if score > best_score:
                best_score = score
                best_type = type_name
        categorized[best_type].append(mem)
    return categorized


def generate_individual_structured_memories(categorized: Dict[str, List[Dict]]) -> List[Dict]:
    structured = []
    for type_name, items in categorized.items():
        for item in items:
            original_text = item["text"]
            cleaned_text = re.sub(r"^\s*\[[a-zA-Z]+\]\s*", "", original_text).strip()
            structured_text = f"[{type_name}] {cleaned_text}"
            structured.append({"id": item["id"], "text": structured_text, "category": type_name})
    return structured


def generate_organized_text(query: str, categorized: Dict[str, List[Dict]]) -> str:
    lines = [f"# 记忆整理 - 主题: {query}", f"## 整理时间: {datetime.now().isoformat()}", ""]
    for type_name in TYPE_DESCRIPTIONS.keys():
        items = categorized.get(type_name, [])
        if items:
            lines.append(f"### {type_name.upper()} ({len(items)}条)")
            for item in items:
                lines.append(f"- {item['text']}")
            lines.append("")
    return "\n".join(lines)


def generate_summary(categorized: Dict[str, List[Dict]]) -> List[Dict]:
    summary = []
    for type_name, items in categorized.items():
        if items:
            preview = " | ".join(item["text"][:50] for item in items[:3])
            if len(preview) > 150:
                preview = preview[:150] + "..."
            summary.append({"category": type_name, "count": len(items), "summary": preview})
    return summary


def organize_memories(query: str, related_memories: List[Dict]) -> Dict:
    if not related_memories:
        return {
            "query": query, "total_found": 0,
            "categories": {t: [] for t in TYPE_DESCRIPTIONS},
            "organized": [], "deleted_ids": [],
            "new_memory_id": None, "individual_memories": []
        }

    categorized = classify_memories(related_memories)
    organized_summary = generate_summary(categorized)
    organized_text = generate_organized_text(query, categorized)
    deleted_ids = [m["id"] for m in related_memories]

    return {
        "query": query, "total_found": len(related_memories),
        "categories": categorized, "organized": organized_summary,
        "deleted_ids": deleted_ids, "organized_text": organized_text,
        "individual_memories": generate_individual_structured_memories(categorized)
    }
