# 认知层 (Cognition Layer)

## 一、项目目标

- **项目名称**：认知层
- **一句话描述**：main_brain 8 层架构的第 6 层。思考、推理、规划、预测——大脑真正"想事情"的地方。
- **核心目标**：
  1. 接收 Attention Layer 的 focus，做有针对性的推理
  2. 管理短期目标/意图（"接下来做什么"）
  3. 预测：根据当前状态预测接下来可能发生什么
  4. 为 Expression Layer 提供"想说的话"的素材
- **不做的事**：
  - 不直接输出消息（那是 Expression Layer）
  - 不直接操作记忆（通过 Memory Layer 接口）

## 二、现有基础

- `modules/brain/state/pending_expression.py` 的 evaluate_and_generate() — 已有扫描 concern/loop 的逻辑
- `modules/brain/state/open_loops.py` — 未解决问题
- `modules/brain/state/goals.py` — 目标

## 三、核心逻辑

```text
cognition.tick():
  1. 读 attention.focus → 知道当前该想什么
  2. 读 memory 获取 focus 相关的记忆
  3. 轻量推理：关注对象有什么新进展？关联什么？
  4. 更新 open_loops：有没有新问题？
  5. 生成 cognition_result（素材）→ 供 Expression Layer
```

## 四、文件清单

```
backend/main_brain/cognition/
  __init__.py
  reasoning.py      # 推理/联想（轻量，非 LLM）
  prediction.py     # 预测模型（LLM）
  goal_manager.py   # 短期目标管理
  open_loops.py     # 迁移现有 OpenLoopManager
```
