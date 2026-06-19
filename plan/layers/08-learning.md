# 学习更新层 (Learning / Update Layer)

## 一、项目目标

- **项目名称**：学习更新层
- **一句话描述**：main_brain 8 层架构的第 8 层。每次行动后根据结果微调模型——记忆巩固、自我叙事更新、关系强化。实现"每次对话都让大脑成长一点点"。
- **核心目标**：
  1. 定期记忆去重与合并（dedup + organize）
  2. 知识图谱边权重衰减与强化（Hebbian）
  3. 自我叙事定期反思更新
  4. 从对话中提取 "lesson" 写入记忆
- **不做的事**：
  - 不调 LLM 做重量级学习（简洁、增量）
  - 不改已有记忆核心

## 二、现有基础

- `modules/brain/memory/core.py` — dedup_memories / organize_memories
- `modules/brain/memory/self_narrative/reflection.py` — daily_reflect
- `modules/brain/graph.py` — increment_co_activation / get_related_entities

## 三、更新频率

| 任务 | 频率 | LLM | 说明 |
|------|------|-----|------|
| 共现强化 | ~15min | ❌ | 增量更新 graph 边权重 |
| 记忆去重 | ~60min | ✅ | 全量扫描相似记忆 |
| lesson 提取 | 每轮对话后 | ✅ | 从 (user, assistant) 对中提取经验 |
| 自我反思 | ~24h | ✅ | daily_reflect |
| 叙事锚点 | 存储后 | ✅ | 现有 pipeline_steps.py |

## 四、文件清单

```
backend/main_brain/learning/
  __init__.py
  consolidation.py  # 记忆巩固（dedup + organize）
  hebbian.py        # 图边权重更新
  reflection.py     # 迁移 self_narrative/reflection.py
  lesson.py         # 对话经验提取
```
