"""
记忆整理模块 - 按类型分类并结构化记忆
"""
import logging
from datetime import datetime
from typing import Dict, List

from .embedding import encode_texts

logger = logging.getLogger(__name__)

# 类型描述向量
TYPE_DESCRIPTIONS = {
    "user": "用户个人信息、偏好、习惯、感受",
    "feedback": "用户反馈、建议、意见、改进想法",
    "project": "项目开发、代码、功能实现、技术任务",
    "reference": "文档、链接、参考资料、学习笔记",
    "ai": "AI 自身的行为、偏好、记忆、经验总结"
}


def classify_memories(memories: List[Dict]) -> Dict[str, List[Dict]]:
    """用 embedding 相似度匹配类型描述，对记忆进行分类。

    Args:
        memories: 记忆列表，每项包含 id, text, timestamp

    Returns:
        按类型分类的字典 {type: [记忆列表]}
    """
    if not memories:
        return {t: [] for t in TYPE_DESCRIPTIONS}

    texts = [m["text"] for m in memories]

    # 编码记忆文本和类型描述
    text_vectors = encode_texts(texts)
    type_vectors = encode_texts(list(TYPE_DESCRIPTIONS.values()))

    # 初始化分类结果
    categorized = {t: [] for t in TYPE_DESCRIPTIONS}

    # 对每条记忆计算与各类型的相似度
    for i, mem in enumerate(memories):
        text_vec = text_vectors[i]
        best_type = "reference"  # 默认类型
        best_score = -1.0

        for j, (type_name, type_desc) in enumerate(TYPE_DESCRIPTIONS.items()):
            type_vec = type_vectors[j]
            # 计算余弦相似度
            score = sum(a * b for a, b in zip(text_vec, type_vec))
            if score > best_score:
                best_score = score
                best_type = type_name

        categorized[best_type].append(mem)

    return categorized


def generate_individual_structured_memories(categorized: Dict[str, List[Dict]]) -> List[Dict]:
    """为每条记忆生成结构化的单独条目。

    Args:
        categorized: 按类型分类的记忆

    Returns:
        结构化后的记忆列表，每项包含 id, text, category
    """
    structured = []
    for type_name, items in categorized.items():
        for item in items:
            # 去掉已有的分类标签（如果原文本以 [xxx] 开头）
            original_text = item["text"]
            import re
            cleaned_text = re.sub(r"^\s*\[[a-zA-Z]+\]\s*", "", original_text).strip()
            # 重新加上正确的分类标签
            structured_text = f"[{type_name}] {cleaned_text}"
            structured.append({
                "id": item["id"],
                "text": structured_text,
                "category": type_name
            })
    return structured


def generate_organized_text(query: str, categorized: Dict[str, List[Dict]]) -> str:
    """生成 Markdown 格式的结构化记忆（仅用于摘要展示）。

    Args:
        query: 整理的主题查询词
        categorized: 按类型分类的记忆

    Returns:
        Markdown 格式的字符串
    """
    lines = [
        f"# 记忆整理 - 主题: {query}",
        f"## 整理时间: {datetime.now().isoformat()}",
        ""
    ]

    # 按顺序遍历类型
    for type_name in TYPE_DESCRIPTIONS.keys():
        items = categorized.get(type_name, [])
        if items:
            lines.append(f"### {type_name.upper()} ({len(items)}条)")
            for item in items:
                lines.append(f"- {item['text']}")
            lines.append("")

    return "\n".join(lines)


def generate_summary(categorized: Dict[str, List[Dict]]) -> List[Dict]:
    """生成整理摘要。

    Args:
        categorized: 按类型分类的记忆

    Returns:
        摘要列表 [{"category": str, "count": int, "summary": str}, ...]
    """
    summary = []
    for type_name, items in categorized.items():
        if items:
            # 取前3条拼接摘要
            preview = " | ".join(item["text"][:50] for item in items[:3])
            if len(preview) > 150:
                preview = preview[:150] + "..."
            summary.append({
                "category": type_name,
                "count": len(items),
                "summary": preview
            })
    return summary


def organize_memories(query: str, related_memories: List[Dict]) -> Dict:
    """整理记忆的主流程。

    Args:
        query: 查询关键词/主题
        related_memories: 通过 search_memory 获取的相关记忆

    Returns:
        整理结果字典
    """
    if not related_memories:
        return {
            "query": query,
            "total_found": 0,
            "categories": {t: [] for t in TYPE_DESCRIPTIONS},
            "organized": [],
            "deleted_ids": [],
            "new_memory_id": None,
            "individual_memories": []
        }

    # 1. 分类
    categorized = classify_memories(related_memories)

    # 2. 生成摘要
    organized_summary = generate_summary(categorized)

    # 3. 生成结构化文本
    organized_text = generate_organized_text(query, categorized)

    # 4. 收集待删除的 ID
    deleted_ids = [m["id"] for m in related_memories]

    return {
        "query": query,
        "total_found": len(related_memories),
        "categories": categorized,
        "organized": organized_summary,
        "deleted_ids": deleted_ids,
        "organized_text": organized_text,
        "individual_memories": generate_individual_structured_memories(categorized)
    }
