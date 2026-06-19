# 状态层 (State Layer)

## 一、项目目标

- **项目名称**：状态层
- **一句话描述**：main_brain 8 层架构的第 5 层。所有内部状态的统一管理与持久化。迁移现有 `modules/brain/state/` 到 `main_brain/state/`。
- **核心目标**：
  1. 迁移现有 InternalState + 所有 Manager（concerns/working_set/open_loops/pending/expression_history）
  2. 保持 transaction() / snapshot() 接口不变
  3. 扩展 emotion/attention/sensory 等新状态字段
- **不做的事**：
  - 不改事务机制（RLock + 原子落盘）
  - 不改现有 Manager 的接口签名

## 二、现有基础

- `modules/brain/state/store.py` — InternalState 单例 + 事务 + 持久化
- `modules/brain/state/concerns.py` — ConcernManager
- `modules/brain/state/working_set.py` — WorkingSetManager
- `modules/brain/state/open_loops.py` — OpenLoopManager
- `modules/brain/state/pending_expression.py` — PendingExpressionManager
- `modules/brain/state/expression_history.py` — ExpressionHistoryManager
- `modules/brain/state/drives.py` — DriveManager
- `modules/brain/state/self_model.py` — SelfModelManager
- `modules/brain/state/times.py` — 时间工具
- `modules/brain/state/__init__.py` — 模块转发

## 三、新增状态字段

```json
{
  "emotion": {"valence": 0.0, "arousal": 0.3, "dominance": 0.5},
  "attention": {"focus": "", "salience_map": {}},
  "sensory": {"last_user_message_at": "", "idle_hours": 0.0},
  "subconscious": {"tick_counts": {}, "last_module_times": {}}
}
```

## 四、文件清单

```
backend/main_brain/state/
  __init__.py       # 保持全部 get_*() 接口
  store.py          # InternalState 单例（同现）
  times.py          # 时间工具（同现）
  concerns.py       # 迁移
  working_set.py    # 迁移
  open_loops.py     # 迁移
  pending_expression.py  # 迁移
  expression_history.py  # 迁移
  drives.py         # 迁移
  self_model.py     # 迁移
  goals.py          # 目标（现有）
```
